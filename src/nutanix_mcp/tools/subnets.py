# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Networks (VLAN-backed subnets) a VM's NIC can attach to."""

from mcp.server.fastmcp import FastMCP

from .. import client as client_mod
from ..config import Settings
from ._common import READ, Filter, Limit, Offset, cap, list_result, run


def _map_subnet(entity: dict) -> dict:
    status = entity.get("status") or {}
    spec = entity.get("spec") or {}
    resources = (status.get("resources") or spec.get("resources") or {})
    cluster_ref = status.get("cluster_reference") or spec.get("cluster_reference") or {}
    return {
        "uuid": (entity.get("metadata") or {}).get("uuid"),
        "name": status.get("name") or spec.get("name"),
        "vlan_id": resources.get("vlan_id"),
        "cluster_uuid": cluster_ref.get("uuid"),
    }


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="nutanix_list_subnets",
        description="List VLAN-backed subnets a VM's NIC can attach to.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_list_subnets(filter: Filter = None, limit: Limit = None, offset: Offset = None) -> str:
        size = cap(limit)
        start = int(offset or 0)

        async def handler(client: client_mod.NutanixClient):
            payload = await client.list_entities("subnets", "subnet", filter_=filter, length=size, offset=start)
            return list_result(payload, _map_subnet, size, start)

        return await run(settings, handler)
