# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Virtual machines: list, get, and the one write tool (power control)."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .. import client as client_mod
from ..config import Settings
from ._common import POWER, READ, Filter, Limit, Offset, cap, list_result, run, seg


def _map_vm(entity: dict) -> dict:
    status = entity.get("status") or {}
    resources = status.get("resources") or {}
    cluster_ref = status.get("cluster_reference") or {}
    return {
        "uuid": (entity.get("metadata") or {}).get("uuid"),
        "name": status.get("name") or (entity.get("spec") or {}).get("name"),
        "power_state": resources.get("power_state"),
        "cluster_uuid": cluster_ref.get("uuid"),
        "cluster_name": cluster_ref.get("name"),
    }


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="nutanix_list_vms",
        description="List virtual machines across the Prism Central environment.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_list_vms(filter: Filter = None, limit: Limit = None, offset: Offset = None) -> str:
        size = cap(limit)
        start = int(offset or 0)

        async def handler(client: client_mod.NutanixClient):
            payload = await client.list_entities("vms", "vm", filter_=filter, length=size, offset=start)
            return list_result(payload, _map_vm, size, start)

        return await run(settings, handler)

    @mcp.tool(
        name="nutanix_get_vm",
        description="Get full spec and status for one VM by uuid.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_get_vm(vm_uuid: str) -> str:
        async def handler(client: client_mod.NutanixClient):
            entity = await client.get_entity("vms", seg(vm_uuid, "vm_uuid"))
            if not isinstance(entity, dict):
                return {}
            return {
                "uuid": (entity.get("metadata") or {}).get("uuid"),
                "spec": entity.get("spec"),
                "status": entity.get("status"),
            }

        return await run(settings, handler)

    @mcp.tool(
        name="nutanix_power_vm",
        description=(
            "Change a VM's power state.\n"
            "Not idempotent: calling the same action twice triggers two transitions. Returns a "
            "task uuid; poll it with nutanix_get_task to know when the transition finished."
        ),
        annotations=POWER,
        structured_output=False,
    )
    async def nutanix_power_vm(
        vm_uuid: str,
        action: Annotated[
            Literal["on", "off", "soft_shutdown", "reboot"], Field(description="Power transition to trigger.")
        ],
    ) -> str:
        async def handler(client: client_mod.NutanixClient):
            return await client.power_vm(seg(vm_uuid, "vm_uuid"), action)

        return await run(settings, handler)
