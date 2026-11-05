# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Thin async client for the Nutanix Prism Central v3 REST API.

Reference: Nutanix Prism Central v3 API (public, self-service, no partner gate — www.nutanix.dev,
confirmed in the PRD-21347 design). Auth is plain HTTP Basic against a Prism Central account.

- Lists: ``POST /api/nutanix/v3/<kind>s/list`` with a common body ``{"kind": "<kind>", "length",
  "offset", "filter"?}``; response is ``{"metadata": {...}, "entities": [...]}``.
- Single resource: ``GET /api/nutanix/v3/<kind>s/{uuid}``.
- VM power control: read-modify-write via ``PUT /api/nutanix/v3/vms/{uuid}`` (the documented v3
  pattern for updating a VM's ``spec``). The exact power_state_mechanism shape for soft-shutdown
  and reboot was not verifiable against the live OpenAPI/Swagger spec during design (PRD-21347
  design doc, Open questions / Risks) and needs confirming against a real Prism Central; the
  external contract this tool promises (a task UUID back) does not change either way.

A client is built fresh per request, from that request's ContextVar credentials only (SOP §3).
"""

import asyncio
import email.utils
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from .config import Settings
from .credentials import Credentials, resolve_base_url

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF = 20.0
USER_AGENT = "mspbots-nutanix-mcp/1.0"

PowerAction = Literal["on", "off", "soft_shutdown", "reboot"]

# resources.power_state / power_state_mechanism to send on PUT /vms/{uuid} for each action.
# See the module docstring: the exact mechanism shape is an open item pending live-spec
# confirmation (does not change the task-uuid contract in AC4).
POWER_ACTIONS: dict[str, dict[str, Any]] = {
    "on": {"power_state": "ON"},
    "off": {"power_state": "OFF", "power_state_mechanism": {"mechanism": "HARD"}},
    "soft_shutdown": {"power_state": "OFF", "power_state_mechanism": {"mechanism": "ACPI"}},
    "reboot": {"power_state": "ON", "power_state_mechanism": {"mechanism": "ACPI"}},
}


@dataclass
class ApiError(Exception):
    code: str
    message: str
    retryable: bool = False
    status: int | None = None

    def __str__(self) -> str:
        return self.message


def _error_detail(response: httpx.Response) -> str:
    """Nutanix's own explanation, from its ``message_list`` error body or plain text."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:500]
    if isinstance(body, dict):
        messages = body.get("message_list")
        if isinstance(messages, list) and messages:
            first = messages[0]
            if isinstance(first, dict) and isinstance(first.get("message"), str) and first["message"].strip():
                return first["message"].strip()[:500]
        for key in ("message", "error", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    if isinstance(body, str):
        return body.strip()[:500]
    return str(body)[:500]


def _status_to_error(status: int, detail: str) -> ApiError:
    if status in (401, 403):
        message = f"Prism Central refused the request ({status}). {detail}".strip()
        return ApiError("unauthorized", message, False, status)
    if status == 404:
        return ApiError("not_found", f"Not found in Prism Central. {detail}".strip(), False, status)
    if status in (400, 422):
        return ApiError(
            "invalid_argument", f"Prism Central rejected the request ({status}). {detail}".strip(), False, status
        )
    if status == 429:
        return ApiError("rate_limited", "Prism Central rate limit reached. Try again shortly.", True, status)
    return ApiError("upstream_error", f"Prism Central returned {status}. {detail}".strip(), status >= 500, status)


def _retry_after(response: httpx.Response, attempt: int) -> float:
    value = response.headers.get("retry-after")
    if value:
        try:
            return min(float(value), MAX_BACKOFF)
        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(value)
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                return max(0.0, min(parsed.timestamp() - time.time(), MAX_BACKOFF))
    return min(2.0 ** max(attempt - 1, 0), MAX_BACKOFF)


class NutanixClient:
    """One instance per tool call; wraps a single httpx client built from this request's credentials."""

    def __init__(self, creds: Credentials, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._base_url = resolve_base_url(creds.host)
        self._deadline = time.monotonic() + settings.call_budget_seconds
        self._http = httpx.AsyncClient(
            auth=httpx.BasicAuth(creds.username, creds.password),
            verify=creds.verify_ssl,
            headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": USER_AGENT},
            timeout=httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout),
            transport=transport,
        )

    async def __aenter__(self) -> "NutanixClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send with retries on 429/5xx/timeouts, honouring Retry-After and the per-call budget.
        Connection-level failures (including TLS verification failures, AC7) are reported as a
        clear ``upstream_error`` rather than left to propagate as an unhandled exception."""
        url = f"{self._base_url}{path}"
        attempt = 0
        while True:
            try:
                response = await self._http.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                if attempt < self._settings.max_retries and time.monotonic() + 1 < self._deadline:
                    attempt += 1
                    await asyncio.sleep(min(2.0 ** max(attempt - 1, 0), MAX_BACKOFF))
                    continue
                raise ApiError("upstream_error", "Prism Central did not respond in time.", True) from exc
            except httpx.HTTPError as exc:
                # Covers connection-refused and TLS/certificate verification failures.
                raise ApiError("upstream_error", f"Could not reach Prism Central: {exc}", True) from exc

            if response.status_code in RETRY_STATUSES and attempt < self._settings.max_retries:
                wait = _retry_after(response, attempt + 1)
                if time.monotonic() + wait < self._deadline:
                    attempt += 1
                    await asyncio.sleep(wait)
                    continue
            return response

    async def request_json(self, method: str, path: str, *, json_body: Any = None) -> Any:
        response = await self._send(method, path, json=json_body)
        if response.status_code >= 400:
            raise _status_to_error(response.status_code, _error_detail(response))
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError("upstream_error", "Prism Central returned a response that is not JSON.", True) from exc

    async def list_entities(self, path: str, kind: str, *, filter_: str | None, length: int, offset: int) -> Any:
        body: dict[str, Any] = {"kind": kind, "length": length, "offset": offset}
        if filter_:
            body["filter"] = filter_
        return await self.request_json("POST", f"/api/nutanix/v3/{path}/list", json_body=body)

    async def get_entity(self, path: str, uuid: str) -> Any:
        return await self.request_json("GET", f"/api/nutanix/v3/{path}/{uuid}")

    async def power_vm(self, vm_uuid: str, action: PowerAction) -> dict[str, Any]:
        current = await self.get_entity("vms", vm_uuid)
        if not isinstance(current, dict):
            raise ApiError("upstream_error", "Prism Central returned an unexpected VM representation.", True)
        resources = current.setdefault("spec", {}).setdefault("resources", {})
        for key in ("power_state_mechanism",):
            resources.pop(key, None)
        resources.update(POWER_ACTIONS[action])
        updated = await self.request_json("PUT", f"/api/nutanix/v3/vms/{vm_uuid}", json_body=current)
        task_uuid = None
        if isinstance(updated, dict):
            task_uuid = (updated.get("status") or {}).get("execution_context", {}).get("task_uuid")
        if not task_uuid:
            raise ApiError("upstream_error", "Prism Central did not return a task UUID for the power operation.", True)
        return {"task_uuid": task_uuid}
