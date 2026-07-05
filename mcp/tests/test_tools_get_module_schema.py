"""Tests for ``get_module_schema``: smoke-test all 9 v1 types."""

from __future__ import annotations

import pytest
from mcp import McpError
from mcp.server.fastmcp.exceptions import ToolError

from app.backend import BackendClient

from ._mcp_helpers import build_mcp_for_tests, call_tool, unwrap_mcp_error
from .conftest import AdminSession, register_agent

ALL_TYPES = [
    "markdown",
    "key_value",
    "table",
    "timeseries",
    "log_stream",
    "link_list",
    "iframe",
    "action_button",
    "notification",
    "progress",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("module_type", ALL_TYPES)
async def test_get_module_schema_returns_each_type(
    mcp_backend_client: BackendClient, admin: AdminSession, module_type: str
) -> None:
    _, key = register_agent(admin, name=f"t-schema-{module_type}")
    mcp = build_mcp_for_tests()
    result = await call_tool(mcp, "get_module_schema", {"type": module_type}, agent_key=key)
    # Each backend response includes at least a data_schema or schema entry —
    # accept either shape.
    assert isinstance(result, dict)
    assert result, "schema response empty"
    config_schema = result.get("config_schema") or result.get("config")
    assert isinstance(config_schema, dict)
    assert "appearance" in config_schema.get("properties", {})


@pytest.mark.asyncio
async def test_get_module_schema_unknown_type_is_not_found(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="t-schema-unknown")
    mcp = build_mcp_for_tests()
    with pytest.raises((McpError, ToolError)) as exc:
        await call_tool(mcp, "get_module_schema", {"type": "nope"}, agent_key=key)
    mcp_err = unwrap_mcp_error(exc.value)
    assert mcp_err is not None
    assert mcp_err.error.code == -32002  # NOT_FOUND
