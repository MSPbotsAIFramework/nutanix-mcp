# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Active alerts raised across the Prism Central environment."""

from mcp.server.fastmcp import FastMCP

from .. import client as client_mod
from ..config import Settings
from ._common import READ, Filter, Limit, Offset, cap, list_result, run


def _map_alert(entity: dict) -> dict:
    # Alert entities are flatter than other v3 kinds (no separate spec/status split); tolerate
    # both shapes so a live-spec difference degrades to missing fields, not a crash.
    status = entity.get("status") or {}
    source = status if status else entity
    uuid = (entity.get("metadata") or {}).get("uuid") or entity.get("uuid")
    title = source.get("title") or source.get("message")
    created_time = source.get("created_time") or entity.get("created_time")
    return {
        "uuid": uuid,
        "title": title,
        "severity": source.get("severity"),
        "created_time": created_time,
    }


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="nutanix_list_alerts",
        description="List active alerts raised across the Prism Central environment.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_list_alerts(filter: Filter = None, limit: Limit = None, offset: Offset = None) -> str:
        size = cap(limit)
        start = int(offset or 0)

        async def handler(client: client_mod.NutanixClient):
            payload = await client.list_entities("alerts", "alert", filter_=filter, length=size, offset=start)
            return list_result(payload, _map_alert, size, start)

        return await run(settings, handler)
