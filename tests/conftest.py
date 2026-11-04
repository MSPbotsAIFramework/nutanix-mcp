# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from nutanix_mcp import credentials
from nutanix_mcp.config import Settings
from nutanix_mcp.server import create_mcp

HOST = "example-pc.local"
BASE = f"https://{HOST}:9440"


@pytest.fixture
def settings() -> Settings:
    # Keep retries fast in tests.
    return Settings(max_retries=1, call_budget_seconds=5)


@pytest.fixture
def mcp(settings):
    return create_mcp(settings)


@pytest.fixture
def creds():
    token = credentials._current.set(
        credentials.Credentials(host=HOST, username="svc-account", password="svc-password", verify_ssl=True)
    )
    yield
    credentials._current.reset(token)


@pytest.fixture
def call(mcp):
    async def _call(tool: str, /, **args):
        result = await mcp.call_tool(tool, args)
        blocks = result[0] if isinstance(result, tuple) else result
        return json.loads(blocks[0].text)

    return _call
