# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Tool behaviour against a mocked Prism Central (TC1, TC3, TC5, TC6, TC7, TC8, TC11)."""

import json

import httpx
import pytest

from conftest import BASE
from nutanix_mcp.tools._common import cap

pytestmark = pytest.mark.usefixtures("creds")

VMS_LIST = f"{BASE}/api/nutanix/v3/vms/list"


def _vm_entity(i: int) -> dict:
    return {
        "metadata": {"uuid": f"vm-{i}"},
        "spec": {"name": f"vm-{i}"},
        "status": {
            "name": f"vm-{i}",
            "resources": {"power_state": "ON"},
            "cluster_reference": {"uuid": "cluster-1", "name": "Cluster One"},
        },
    }


def _sent_body(route) -> dict:
    return json.loads(route.calls.last.request.content)


async def test_tools_list_returns_nutanix_toolset(mcp):
    # TC1 (AC1): the full tool set, with descriptions and typed parameters, no Prism Central call.
    tools = {t.name: t for t in await mcp.list_tools()}
    expected = {
        "nutanix_list_vms",
        "nutanix_get_vm",
        "nutanix_power_vm",
        "nutanix_list_clusters",
        "nutanix_get_cluster",
        "nutanix_list_hosts",
        "nutanix_get_host",
        "nutanix_list_images",
        "nutanix_list_subnets",
        "nutanix_list_storage_containers",
        "nutanix_get_task",
        "nutanix_list_alerts",
    }
    assert set(tools) == expected
    for name, tool in tools.items():
        assert tool.description, name
        assert len(tool.description) <= 500, name
        assert tool.description.splitlines()[0].__len__() <= 100, name
    power = tools["nutanix_power_vm"]
    assert set(power.inputSchema["required"]) >= {"vm_uuid", "action"}
    assert power.annotations.destructiveHint is True
    assert power.annotations.readOnlyHint is False
    assert tools["nutanix_list_vms"].annotations.readOnlyHint is True


async def test_list_vms_returns_mapped_fields_and_has_more(respx_mock, call):
    # TC3 (AC3): up to 50 mapped VM records, has_more set correctly against a mocked Prism Central.
    entities = [_vm_entity(i) for i in range(50)]
    route = respx_mock.post(VMS_LIST).mock(
        return_value=httpx.Response(200, json={"metadata": {"total_matches": 75}, "entities": entities})
    )
    out = await call("nutanix_list_vms")
    assert _sent_body(route) == {"kind": "vm", "length": 50, "offset": 0}
    assert out["count"] == 50
    assert out["has_more"] is True
    assert out["items"][0] == {
        "uuid": "vm-0",
        "name": "vm-0",
        "power_state": "ON",
        "cluster_uuid": "cluster-1",
        "cluster_name": "Cluster One",
    }


async def test_list_vms_has_more_false_when_all_matches_returned(respx_mock, call):
    entities = [_vm_entity(i) for i in range(10)]
    respx_mock.post(VMS_LIST).mock(
        return_value=httpx.Response(200, json={"metadata": {"total_matches": 10}, "entities": entities})
    )
    out = await call("nutanix_list_vms")
    assert out["has_more"] is False
    assert out["total_count"] == 10


async def test_power_vm_returns_task_uuid(respx_mock, call):
    # TC5 (AC4): read-modify-write returns the triggered task uuid.
    uuid = "vm-123"
    current = {
        "metadata": {"uuid": uuid, "spec_version": 3},
        "spec": {"name": "vm-123", "resources": {"power_state": "OFF"}},
        "status": {"name": "vm-123"},
    }
    respx_mock.get(f"{BASE}/api/nutanix/v3/vms/{uuid}").mock(return_value=httpx.Response(200, json=current))
    put_route = respx_mock.put(f"{BASE}/api/nutanix/v3/vms/{uuid}").mock(
        return_value=httpx.Response(200, json={"status": {"execution_context": {"task_uuid": "task-789"}}})
    )
    out = await call("nutanix_power_vm", vm_uuid=uuid, action="reboot")
    assert out == {"task_uuid": "task-789"}
    sent = _sent_body(put_route)
    assert sent["spec"]["resources"]["power_state"] == "ON"
    assert sent["spec"]["resources"]["power_state_mechanism"] == {"mechanism": "ACPI"}


async def test_power_vm_unknown_uuid_returns_not_found_error(respx_mock, call):
    # TC6 (AC4): a structured not_found error, not a 500 or a raw stack trace.
    uuid = "does-not-exist"
    error_body = {"api_version": "3.1", "code": 404, "kind": "error", "message_list": [{"message": "VM not found"}]}
    respx_mock.get(f"{BASE}/api/nutanix/v3/vms/{uuid}").mock(return_value=httpx.Response(404, json=error_body))
    out = await call("nutanix_power_vm", vm_uuid=uuid, action="off")
    assert out["error"]["code"] == "not_found"
    assert out["error"]["retryable"] is False
    assert "VM not found" in out["error"]["message"]


async def test_upstream_5xx_and_timeout_map_to_retryable_upstream_error(respx_mock, call):
    # TC7 (AC5)
    respx_mock.post(VMS_LIST).mock(return_value=httpx.Response(503, json={"message_list": [{"message": "busy"}]}))
    out = await call("nutanix_list_vms")
    assert out["error"] == {"code": "upstream_error", "message": out["error"]["message"], "retryable": True}

    respx_mock.post(VMS_LIST).mock(side_effect=httpx.ReadTimeout("timed out"))
    out = await call("nutanix_list_vms")
    assert out["error"]["code"] == "upstream_error"
    assert out["error"]["retryable"] is True


async def test_upstream_401_maps_to_unauthorized_error(respx_mock, call):
    # TC8 (AC5)
    respx_mock.post(VMS_LIST).mock(
        return_value=httpx.Response(
            401, json={"api_version": "3.1", "code": 401, "kind": "error", "message_list": [{"message": "bad creds"}]}
        )
    )
    out = await call("nutanix_list_vms")
    assert out["error"]["code"] == "unauthorized"
    assert out["error"]["retryable"] is False
    assert "bad creds" in out["error"]["message"]


async def test_list_limit_defaults_to_50_and_caps_at_200(respx_mock, call):
    # TC11 (AC8)
    assert cap(None) == 50
    assert cap(1000) == 200
    assert cap(0) == 50  # falsy limit is treated as "not specified" -> default
    assert cap(-5) == 1  # floored, never zero/negative

    route = respx_mock.post(VMS_LIST).mock(
        return_value=httpx.Response(200, json={"metadata": {"total_matches": 0}, "entities": []})
    )
    await call("nutanix_list_vms", limit=1000)
    assert _sent_body(route)["length"] == 200

    await call("nutanix_list_vms")
    assert _sent_body(route)["length"] == 50


async def test_missing_credentials_is_not_configured_error(call):
    from nutanix_mcp import credentials

    token = credentials._current.set(None)
    try:
        out = await call("nutanix_list_vms")
    finally:
        credentials._current.reset(token)
    assert out["error"]["code"] == "not_configured"
