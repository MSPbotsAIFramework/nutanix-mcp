# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""FastMCP server and HTTP app."""

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .arguments import EnvelopeFastMCP
from .config import Settings
from .credentials import CredentialMiddleware
from .tools import alerts, clusters, hosts, images, storage, subnets, tasks, vms

INSTRUCTIONS = (
    "Nutanix Prism Central manages one or more Nutanix clusters (hyperconverged infrastructure: "
    "compute, storage, networking). Start from a cluster with nutanix_list_clusters, then list "
    "hosts, VMs, images, subnets or storage containers on it. nutanix_list_vms returns VM uuids "
    "and power_state; use nutanix_get_vm for full detail on one VM. nutanix_power_vm is the only "
    "write tool: it triggers a power transition (on/off/soft_shutdown/reboot) and returns a task "
    "uuid — poll it with nutanix_get_task until status is COMPLETE. nutanix_list_alerts surfaces "
    "active issues across the environment. Ask the user before calling nutanix_power_vm."
)


def create_mcp(settings: Settings) -> EnvelopeFastMCP:
    mcp = EnvelopeFastMCP(
        name="nutanix-mcp",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        # The gateway forwards requests with its own Host header; DNS-rebinding protection
        # would otherwise reject them with 421 (SOP §7).
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for module in (vms, clusters, hosts, images, subnets, storage, tasks, alerts):
        module.register(mcp, settings)
    return mcp


def create_app(settings: Settings) -> Starlette:
    mcp = create_mcp(settings)
    mcp_app = mcp.streamable_http_app()

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # Mount() does not run a sub-app's lifespan; without forwarding it the session manager
    # never starts and /mcp fails with "Task group is not initialized" while /health still
    # passes (SOP §7).
    return Starlette(
        routes=[Route("/health", health), Mount("/", app=CredentialMiddleware(mcp_app))],
        lifespan=lambda app: mcp_app.router.lifespan_context(app),
    )
