# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Per-request credentials, taken only from request headers (PRD-21347 AC2, AC6).

The gateway sends each tenant's Prism Central credentials on every request. They live in a
ContextVar for the duration of that request and are never stored anywhere else (no globals,
no module-level cache) so concurrent requests from different tenants cannot observe each
other's credentials or connection.
"""

import contextvars
from dataclasses import dataclass
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import DEFAULT_PORT, HOST_HEADER, PASSWORD_HEADER, REQUIRED_HEADERS, USERNAME_HEADER, VERIFY_SSL_HEADER


@dataclass(frozen=True)
class Credentials:
    host: str
    username: str
    password: str
    verify_ssl: bool = True


_current: contextvars.ContextVar[Credentials | None] = contextvars.ContextVar("nutanix_credentials", default=None)


def current() -> Credentials | None:
    return _current.get()


class CredentialError(ValueError):
    """A header was present but not usable (e.g. an empty host)."""


_FALSE_VALUES = {"false", "0", "no", "off"}


def _parse_verify_ssl(value: str | None) -> bool:
    """Default is verify-on (AC7); the header is an explicit per-request opt-out, not a toggle."""
    if value is None:
        return True
    return value.strip().lower() not in _FALSE_VALUES


def resolve_base_url(host: str) -> str:
    """``acme-pc.example.com`` -> ``https://acme-pc.example.com:9440``; a host that already
    carries a scheme and/or port (``https://acme-pc.example.com:9441``) is respected as-is."""
    text = host.strip().rstrip("/")
    if not text:
        raise CredentialError(f"{HOST_HEADER} must not be empty.")
    if "://" in text:
        scheme, _, rest = text.partition("://")
    else:
        scheme, rest = "https", text
    authority = rest.split("/", 1)[0]
    hostname = urlparse(f"//{authority}").hostname
    if not hostname:
        raise CredentialError(f"{HOST_HEADER} is not a valid host: {host!r}.")
    port = urlparse(f"//{authority}").port or DEFAULT_PORT
    return f"{scheme}://{hostname}:{port}"


def _reject(missing: list[str]) -> JSONResponse:
    return JSONResponse({"error": "missing_headers", "missing": missing}, status_code=401)


class CredentialMiddleware:
    """Reads the Nutanix headers on /mcp requests and binds them to the request context."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        headers = Request(scope).headers
        values = {name: (headers.get(name) or "").strip() for name in REQUIRED_HEADERS}
        missing = [name for name in REQUIRED_HEADERS if not values[name]]
        if missing:
            await _reject(missing)(scope, receive, send)
            return

        token = _current.set(
            Credentials(
                host=values[HOST_HEADER],
                username=values[USERNAME_HEADER],
                password=values[PASSWORD_HEADER],
                verify_ssl=_parse_verify_ssl(headers.get(VERIFY_SSL_HEADER)),
            )
        )
        try:
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)
