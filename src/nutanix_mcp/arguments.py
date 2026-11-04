# Copyright 2026 MSPbots.ai
# SPDX-License-Identifier: Apache-2.0
"""Invalid tool arguments reported as the standard invalid_argument envelope (SOP §4.2).

FastMCP checks arguments (required, type, range) before the tool runs and otherwise answers with
its own "Error executing tool ..." text instead of the structured envelope every other error uses.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from . import json_utils


class EnvelopeFastMCP(FastMCP):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            return await super().call_tool(name, arguments)
        except ToolError as error:
            if not isinstance(error.__cause__, ValidationError):
                raise
            problems = "; ".join(_describe(e) for e in error.__cause__.errors())
            envelope = json_utils.error("invalid_argument", f"Invalid arguments for {name}: {problems}.")
            return self._tool_manager.get_tool(name).fn_metadata.convert_result(envelope)


def _describe(error: Any) -> str:
    # Names the argument and what is wrong with it; the rejected value itself is not echoed.
    where = ".".join(str(part) for part in error.get("loc", ())) or "arguments"
    return f"{where}: {error.get('msg', 'invalid value')}"
