# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Storage containers (the datastore-equivalent unit VM disks are placed on).

The exact v3 collection path for storage containers (flat ``.../list`` vs. the Groups API) was
not verifiable against the live OpenAPI/Swagger spec during design (PRD-21347 design doc, Open
questions); this uses the same ``.../list`` shape every other v3 kind in this server uses, and
needs confirming against a real Prism Central. The external tool contract (a read-only list of
storage containers) does not change either way.
"""

from mcp.server.fastmcp import FastMCP

from .. import client as client_mod
from ..config import Settings
from ._common import READ, Filter, Limit, Offset, cap, list_result, run


def _map_storage_container(entity: dict) -> dict:
    status = entity.get("status") or {}
    spec = entity.get("spec") or {}
    cluster_ref = status.get("cluster_reference") or spec.get("cluster_reference") or {}
    return {
        "uuid": (entity.get("metadata") or {}).get("uuid"),
        "name": status.get("name") or spec.get("name"),
        "cluster_uuid": cluster_ref.get("uuid"),
    }


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="nutanix_list_storage_containers",
        description="List storage containers (datastore-equivalent) available for VM disks.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_list_storage_containers(filter: Filter = None, limit: Limit = None, offset: Offset = None) -> str:
        size = cap(limit)
        start = int(offset or 0)

        async def handler(client: client_mod.NutanixClient):
            payload = await client.list_entities(
                "storage_containers", "storage_container", filter_=filter, length=size, offset=start
            )
            return list_result(payload, _map_storage_container, size, start)

        return await run(settings, handler)
