# nutanix-mcp

MCP server for Nutanix Prism Central, built for the MSPbots Agent Platform. It gives any
MCP-compatible agent (Claude, ChatGPT, Cursor, or the MSPbots Agent Platform itself) live,
read-mostly access to a customer's Nutanix Prism Central environment — clusters, hosts, VMs,
images, subnets, storage containers, tasks and alerts — plus one bounded write action, VM power
control.

- **Transport**: MCP Streamable HTTP (`POST /mcp`), stateless, JSON-RPC 2.0.
- **Tech stack**: Python 3.12, FastMCP, httpx.
- **License**: Apache-2.0 (see `LICENSE`).

---

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

Every `/mcp` request must carry this connector's credentials as HTTP headers. None are read from
environment variables (SOP §3.1): a missing required header returns `401` naming it.

| Header | Required | Meaning | Where to get it |
|---|---|---|---|
| `X-Nutanix-Host` | Yes | Prism Central hostname or IP, optionally `host:port`. Defaults to port `9440` if no port is given. | Your Prism Central instance's address |
| `X-Nutanix-Username` | Yes | Prism Central account username. Any role with read access to the resources below; a role with write access is additionally required to call `nutanix_power_vm`. | Prism Central → Administration → Local User Management (or your SSO/LDAP provider) |
| `X-Nutanix-Password` | Yes | Password for the account above. | — |
| `X-Nutanix-Verify-Ssl` | No | `"true"` (default) or `"false"`. Set to `"false"` to accept the self-signed certificate most on-prem Prism Central instances present out of the box. | — |

## Tools

All tool names are prefixed `nutanix_`. List tools accept `filter` (a Prism Central filter
expression), `limit` (default 50, capped at 200) and `offset`.

| Tool | Params | Returns | Annotations |
|---|---|---|---|
| `nutanix_list_vms` | `filter?`, `limit?`, `offset?` | `{"items":[{uuid,name,power_state,cluster_uuid,cluster_name}], "has_more":bool}` | read-only |
| `nutanix_get_vm` | `vm_uuid` | VM `spec` + `status` | read-only |
| `nutanix_power_vm` | `vm_uuid`, `action: on\|off\|soft_shutdown\|reboot` | `{"task_uuid": "..."}` | **destructive, not idempotent** |
| `nutanix_list_clusters` | `filter?`, `limit?`, `offset?` | `{"items":[{uuid,name,version}], "has_more":bool}` | read-only |
| `nutanix_get_cluster` | `cluster_uuid` | cluster `spec` + `status` | read-only |
| `nutanix_list_hosts` | `filter?`, `limit?`, `offset?` | `{"items":[{uuid,name,cluster_uuid,hypervisor}], "has_more":bool}` | read-only |
| `nutanix_get_host` | `host_uuid` | host `spec` + `status` | read-only |
| `nutanix_list_images` | `filter?`, `limit?`, `offset?` | `{"items":[{uuid,name,image_type}], "has_more":bool}` | read-only |
| `nutanix_list_subnets` | `filter?`, `limit?`, `offset?` | `{"items":[{uuid,name,vlan_id,cluster_uuid}], "has_more":bool}` | read-only |
| `nutanix_list_storage_containers` | `filter?`, `limit?`, `offset?` | `{"items":[{uuid,name,cluster_uuid}], "has_more":bool}` | read-only |
| `nutanix_get_task` | `task_uuid` | `{"uuid","status","percentage_complete"}` | read-only, idempotent |
| `nutanix_list_alerts` | `filter?`, `limit?`, `offset?` | `{"items":[{uuid,title,severity,created_time}], "has_more":bool}` | read-only |

### Errors

Every tool returns a JSON string. On success, the result body (see table above); on failure, the
shared envelope:

```json
{"error": {"code": "unauthorized", "message": "...", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`, `rate_limited`,
`upstream_error`. `retryable` tells the caller whether retrying the same call might succeed.

## Running locally

```bash
uv sync
uv run python -m nutanix_mcp
```

The server listens on `http://0.0.0.0:8080`. Send your own test Prism Central's credentials as
headers (never commit them):

```bash
curl -s http://localhost:8080/health

curl -s -X POST http://localhost:8080/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H 'X-Nutanix-Host: your-pc.example.com' \
  -H 'X-Nutanix-Username: your-username' \
  -H 'X-Nutanix-Password: your-password' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Tests

```bash
uv run pytest
```

Unit tests mock Prism Central (`respx`); there is no live Prism Central in this pipeline's
environment, so end-to-end behavior against a real cluster — including the self-signed-certificate
path (`X-Nutanix-Verify-Ssl`) — is marked `manual` / needs a real vendor account in
`docs/tickets/PRD-21347.ac.json` rather than skipped silently.

## Scope (first version)

Core Prism Central infrastructure management only: clusters, hosts, VMs, images, subnets, storage
containers, tasks and alerts, plus VM power control. Not covered in this version: Nutanix Files,
Objects, Era/NDB, Move, Calm/Self-Service, licensing or multi-cluster DR orchestration; VM
create/clone/delete/resize, snapshot/restore, or network reconfiguration; Prism Element
(single-cluster, pre-Prism-Central) APIs; the Prism Central v4 API (deferred — see
`docs/tickets/PRD-21347.md`).
