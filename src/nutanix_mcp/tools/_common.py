# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Shared plumbing for tool handlers."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from .. import json_utils
from ..client import ApiError, NutanixClient
from ..config import HOST_HEADER, PASSWORD_HEADER, USERNAME_HEADER, Settings
from ..credentials import CredentialError, current

log = logging.getLogger("nutanix_mcp")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
POWER = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)

Filter = Annotated[
    str | None,
    Field(description="Prism Central filter expression (e.g. 'power_state==on'); omit to match all."),
]
Limit = Annotated[
    int | None, Field(description=f"Maximum number of results (default {DEFAULT_LIMIT}, capped at {MAX_LIMIT}).")
]
Offset = Annotated[int | None, Field(description="Record position to start from (0-based).", ge=0)]


def cap(limit: int | None, default: int = DEFAULT_LIMIT, maximum: int = MAX_LIMIT) -> int:
    """AC8 / TC11: no limit -> default; limit above the hard cap -> capped, never passed through unbounded."""
    return min(max(int(limit or default), 1), maximum)


class ToolInputError(ValueError):
    """Raised by handlers for arguments Prism Central would reject anyway."""


def seg(value: str, label: str = "uuid") -> str:
    """A Prism Central UUID used in a URL path: non-empty, no path-breaking characters."""
    text = str(value).strip()
    if not text or "/" in text or text != value.strip():
        raise ToolInputError(f"{label} must be a non-empty Prism Central UUID, got {value!r}.")
    return text


def list_result(payload: Any, mapper: Callable[[dict[str, Any]], dict[str, Any]], length: int, offset: int) -> dict:
    """Standard list result from a v3 ``.../list`` response: ``{"metadata": {...}, "entities": [...]}``."""
    entities = payload.get("entities", []) if isinstance(payload, dict) else []
    total = (payload.get("metadata") or {}).get("total_matches") if isinstance(payload, dict) else None
    items = [mapper(e) for e in entities if isinstance(e, dict)]
    out: dict[str, Any] = {"items": items, "count": len(items), "limit": length, "offset": offset}
    has_more = (offset + len(items)) < total if isinstance(total, int) else len(items) >= length
    out["has_more"] = has_more
    if isinstance(total, int):
        out["total_count"] = total
    return out


Handler = Callable[[NutanixClient], Awaitable[Any]]


async def run(settings: Settings, handler: Handler) -> str:
    """Execute ``handler`` with a client bound to this request's credentials.

    Always returns a string: the JSON result, or the SOP §4.2 error envelope. Never raises —
    every tool in this server goes through this function (AC5).
    """
    creds = current()
    if creds is None:
        return json_utils.error(
            "not_configured",
            f"No Nutanix credentials. Send {HOST_HEADER}, {USERNAME_HEADER} and {PASSWORD_HEADER}.",
        )
    try:
        async with NutanixClient(creds, settings) as client:
            result = await handler(client)
    except CredentialError as exc:
        return json_utils.error("not_configured", str(exc))
    except ApiError as exc:
        return json_utils.error(exc.code, exc.message, exc.retryable)
    except ToolInputError as exc:
        return json_utils.error("invalid_argument", str(exc))
    except Exception:  # noqa: BLE001 - tools must never raise (AC5)
        log.exception("unexpected error in tool handler")
        return json_utils.error("upstream_error", "Unexpected error while calling Prism Central.", True)
    return result if isinstance(result, str) else json_utils.dump(result)
