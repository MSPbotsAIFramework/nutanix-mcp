# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Clusters (the top-level unit Prism Central manages)."""

from mcp.server.fastmcp import FastMCP

from .. import client as client_mod
from ..config import Settings
from ._common import READ, Filter, Limit, Offset, cap, list_result, run, seg


def _map_cluster(entity: dict) -> dict:
    status = entity.get("status") or {}
    resources = status.get("resources") or {}
    software_map = (resources.get("config") or {}).get("software_map") or {}
    version = (software_map.get("NOS") or {}).get("version")
    return {
        "uuid": (entity.get("metadata") or {}).get("uuid"),
        "name": status.get("name") or (entity.get("spec") or {}).get("name"),
        "version": version,
    }


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="nutanix_list_clusters",
        description="List clusters registered with this Prism Central.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_list_clusters(filter: Filter = None, limit: Limit = None, offset: Offset = None) -> str:
        size = cap(limit)
        start = int(offset or 0)

        async def handler(client: client_mod.NutanixClient):
            payload = await client.list_entities("clusters", "cluster", filter_=filter, length=size, offset=start)
            return list_result(payload, _map_cluster, size, start)

        return await run(settings, handler)

    @mcp.tool(
        name="nutanix_get_cluster",
        description="Get full spec and status for one cluster by uuid.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_get_cluster(cluster_uuid: str) -> str:
        async def handler(client: client_mod.NutanixClient):
            entity = await client.get_entity("clusters", seg(cluster_uuid, "cluster_uuid"))
            if not isinstance(entity, dict):
                return {}
            return {
                "uuid": (entity.get("metadata") or {}).get("uuid"),
                "spec": entity.get("spec"),
                "status": entity.get("status"),
            }

        return await run(settings, handler)
