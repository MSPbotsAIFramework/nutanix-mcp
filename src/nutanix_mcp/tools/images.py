# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""VM disk/ISO images available for provisioning."""

from mcp.server.fastmcp import FastMCP

from .. import client as client_mod
from ..config import Settings
from ._common import READ, Filter, Limit, Offset, cap, list_result, run


def _map_image(entity: dict) -> dict:
    status = entity.get("status") or {}
    resources = status.get("resources") or {}
    return {
        "uuid": (entity.get("metadata") or {}).get("uuid"),
        "name": status.get("name") or (entity.get("spec") or {}).get("name"),
        "image_type": resources.get("image_type"),
    }


def register(mcp: FastMCP, settings: Settings) -> None:
    @mcp.tool(
        name="nutanix_list_images",
        description="List disk/ISO images available for provisioning.",
        annotations=READ,
        structured_output=False,
    )
    async def nutanix_list_images(filter: Filter = None, limit: Limit = None, offset: Offset = None) -> str:
        size = cap(limit)
        start = int(offset or 0)

        async def handler(client: client_mod.NutanixClient):
            payload = await client.list_entities("images", "image", filter_=filter, length=size, offset=start)
            return list_result(payload, _map_image, size, start)

        return await run(settings, handler)
