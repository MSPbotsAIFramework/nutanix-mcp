# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Prism Central tasks (poll target for nutanix_power_vm)."""

from mcp.server.fastmcp import FastMCP

from .. import client as client_mod
from ..config import Settings
from ._common import READ, run, seg


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="nutanix_get_task",
        description="Get the status and progress of a Prism Central task by uuid. Safe to poll repeatedly.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_get_task(task_uuid: str) -> str:
        async def handler(client: client_mod.NutanixClient):
            payload = await client.get_entity("tasks", seg(task_uuid, "task_uuid"))
            if not isinstance(payload, dict):
                return {}
            return {
                "uuid": payload.get("uuid"),
                "status": payload.get("status"),
                "percentage_complete": payload.get("percentage_complete"),
            }

        return await run(settings, handler)
