# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""TC2, TC9, TC12: credential headers, request-level isolation, and /health."""

import asyncio

import pytest
from starlette.testclient import TestClient

from nutanix_mcp import credentials
from nutanix_mcp.config import HOST_HEADER, PASSWORD_HEADER, USERNAME_HEADER, VERIFY_SSL_HEADER, Settings
from nutanix_mcp.credentials import CredentialMiddleware
from nutanix_mcp.server import create_app

LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
CREDS = {HOST_HEADER: "pc.example.com", USERNAME_HEADER: "svc", PASSWORD_HEADER: "pw"}


@pytest.fixture
def client():
    with TestClient(create_app(Settings())) as c:
        yield c


def test_health_endpoint_does_not_require_credentials(client):
    # TC12 (AC9): /health never contacts Prism Central and needs no headers.
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_missing_credential_headers_returns_401_and_names_them(client):
    # TC2 (AC2): no request to Prism Central is made (no mock installed, so one would raise/hang).
    r = client.post("/mcp", json=LIST, headers=HEADERS)
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "missing_headers"
    assert set(body["missing"]) == {HOST_HEADER, USERNAME_HEADER, PASSWORD_HEADER}


def test_partial_missing_headers_names_only_the_missing_ones(client):
    h = {**HEADERS, HOST_HEADER: "pc.example.com"}
    r = client.post("/mcp", json=LIST, headers=h)
    assert r.status_code == 401
    assert r.json()["missing"] == [USERNAME_HEADER, PASSWORD_HEADER]


def test_valid_headers_reach_tools_list(client):
    h = {**HEADERS, **CREDS}
    r = client.post("/mcp", json=LIST, headers=h)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert "nutanix_list_vms" in names and "nutanix_power_vm" in names


def test_initialize_then_list(client):
    h = {**HEADERS, **CREDS}
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    }
    assert client.post("/mcp", json=init, headers=h).status_code == 200
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert client.post("/mcp", json=note, headers=h).status_code in (200, 202)
    assert client.post("/mcp", json=LIST, headers=h).status_code == 200


def test_concurrent_requests_do_not_share_credentials_or_client():
    # TC9 (AC6): two concurrent requests with different hosts/credentials must never observe
    # each other's ContextVar value.
    observed: list[tuple[str, str]] = []

    async def app(scope, receive, send):
        before = credentials.current().host
        await asyncio.sleep(0.01)
        observed.append((before, credentials.current().host))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = CredentialMiddleware(app)

    def scope(host: bytes) -> dict:
        return {
            "type": "http",
            "path": "/mcp",
            "headers": [
                (b"x-nutanix-host", host),
                (b"x-nutanix-username", b"svc"),
                (b"x-nutanix-password", b"pw"),
            ],
        }

    async def both():
        await asyncio.gather(
            middleware(scope(b"tenant-a.example.com"), receive, send),
            middleware(scope(b"tenant-b.example.com"), receive, send),
        )

    asyncio.run(both())
    assert sorted(observed) == [
        ("tenant-a.example.com", "tenant-a.example.com"),
        ("tenant-b.example.com", "tenant-b.example.com"),
    ]
    assert credentials.current() is None


@pytest.mark.parametrize(
    ("header_value", "expected"),
    [(None, True), ("true", True), ("True", True), ("false", False), ("FALSE", False), ("0", False), ("no", False)],
)
def test_verify_ssl_header_parsing(client, header_value, expected):
    h = {**HEADERS, **CREDS}
    if header_value is not None:
        h[VERIFY_SSL_HEADER] = header_value
    captured: dict = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    async def app(scope, _receive, _send):
        captured["verify_ssl"] = credentials.current().verify_ssl

    scope = {
        "type": "http",
        "path": "/mcp",
        "headers": [(k.lower().encode(), v.encode()) for k, v in h.items()],
    }
    asyncio.run(CredentialMiddleware(app)(scope, receive, send))
    assert captured["verify_ssl"] is expected


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("pc.example.com", "https://pc.example.com:9440"),
        ("pc.example.com:9441", "https://pc.example.com:9441"),
        ("https://pc.example.com", "https://pc.example.com:9440"),
        ("https://pc.example.com:9441/", "https://pc.example.com:9441"),
    ],
)
def test_resolve_base_url(host, expected):
    assert credentials.resolve_base_url(host) == expected


def test_resolve_base_url_rejects_empty_host():
    with pytest.raises(credentials.CredentialError):
        credentials.resolve_base_url("   ")
