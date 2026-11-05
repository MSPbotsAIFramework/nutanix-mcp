# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Hosts (hypervisor nodes within a cluster)."""

from mcp.server.fastmcp import FastMCP

from .. import client as client_mod
from ..config import Settings
from ._common import READ, Filter, Limit, Offset, cap, list_result, run, seg


def _map_host(entity: dict) -> dict:
    status = entity.get("status") or {}
    resources = status.get("resources") or {}
    hypervisor = resources.get("hypervisor") or {}
    cluster_ref = status.get("cluster_reference") or {}
    return {
        "uuid": (entity.get("metadata") or {}).get("uuid"),
        "name": status.get("name") or (entity.get("spec") or {}).get("name"),
        "cluster_uuid": cluster_ref.get("uuid"),
        "hypervisor": hypervisor.get("hypervisor_full_name") or hypervisor.get("type"),
    }


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="nutanix_list_hosts",
        description="List hypervisor hosts across the Prism Central environment.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_list_hosts(filter: Filter = None, limit: Limit = None, offset: Offset = None) -> str:
        size = cap(limit)
        start = int(offset or 0)

        async def handler(client: client_mod.NutanixClient):
            payload = await client.list_entities("hosts", "host", filter_=filter, length=size, offset=start)
            return list_result(payload, _map_host, size, start)

        return await run(settings, handler)

    @mcp.tool(
        name="nutanix_get_host",
        description="Get full spec and status for one host by uuid.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_get_host(host_uuid: str) -> str:
        async def handler(client: client_mod.NutanixClient):
            entity = await client.get_entity("hosts", seg(host_uuid, "host_uuid"))
            if not isinstance(entity, dict):
                return {}
            return {
                "uuid": (entity.get("metadata") or {}).get("uuid"),
                "spec": entity.get("spec"),
                "status": entity.get("status"),
            }

        return await run(settings, handler)
