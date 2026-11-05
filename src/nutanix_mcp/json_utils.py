# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Compact, size-capped JSON for tool results and the shared error envelope (SOP §2.5, §4.2)."""

import json
from typing import Any

MAX_CHARS = 20_000

ERROR_CODES = {
    "not_configured",
    "unauthorized",
    "not_found",
    "invalid_argument",
    "rate_limited",
    "upstream_error",
}


def compact(data: Any) -> str:
    # No indent (pure token waste) and ensure_ascii=False (escaping doubles token cost for non-ASCII).
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)


def dump(data: Any, max_chars: int = MAX_CHARS) -> str:
    """Serialize ``data`` within ``max_chars``. A dict with an ``items`` list has that list cut
    to the largest prefix that fits, with ``has_more``/``truncated`` set so the caller knows to
    narrow the query rather than silently losing records off a page it thought was complete."""
    text = compact(data)
    if len(text) <= max_chars:
        return text

    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data["items"]
        lo, hi = 0, len(items)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            candidate = {**data, "items": items[:mid], "count": mid, "has_more": True, "truncated": True}
            if len(compact(candidate)) <= max_chars:
                lo = mid
            else:
                hi = mid - 1
        result = {
            **data,
            "items": items[:lo],
            "count": lo,
            "has_more": True,
            "truncated": True,
            "note": (
                f"Result too large to return in full; returned {lo} of {len(items)} items. "
                "Narrow with a filter or a smaller limit."
            ),
        }
        return compact(result)

    return compact(
        {"truncated": True, "note": f"Result too large to return ({len(text)} chars); narrow the request."}
    )


def error(code: str, message: str, retryable: bool = False) -> str:
    assert code in ERROR_CODES, code
    return compact({"error": {"code": code, "message": message, "retryable": retryable}})
