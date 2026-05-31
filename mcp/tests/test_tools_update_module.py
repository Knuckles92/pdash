"""Tests for the ``update_module`` MCP tool."""

from __future__ import annotations

import pytest
from mcp import McpError
from mcp.server.fastmcp.exceptions import ToolError

from app.backend import BackendClient

from ._mcp_helpers import build_mcp_for_tests, call_tool, unwrap_mcp_error
from .conftest import AdminSession, home_page_id, register_agent


def _seed_agent_module(admin: AdminSession, agent_id: str, page_id: str) -> dict:
    r = admin.client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "starter"},
            "config": {},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_update_module_self_owner_auto_applies(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    agent_id, key = register_agent(admin, name="t-upd-self")
    page_id = home_page_id(admin)
    mod = _seed_agent_module(admin, agent_id, page_id)
    mcp = build_mcp_for_tests()
    result = await call_tool(
        mcp,
        "update_module",
        {"module_id": mod["id"], "data": {"body": "v2"}},
        agent_key=key,
    )
    assert result["status"] == "applied", result
    assert result["module"]["data"]["body"] == "v2"


@pytest.mark.asyncio
async def test_update_module_expected_version_forwarded_as_etag(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    """Stale ``expected_version`` triggers an MCP conflict error."""
    agent_id, key = register_agent(admin, name="t-upd-version")
    page_id = home_page_id(admin)
    mod = _seed_agent_module(admin, agent_id, page_id)
    mcp = build_mcp_for_tests()
    with pytest.raises((McpError, ToolError)) as exc:
        await call_tool(
            mcp,
            "update_module",
            {
                "module_id": mod["id"],
                "data": {"body": "stale"},
                "expected_version": 999,  # wrong
            },
            agent_key=key,
        )
    mcp_err = unwrap_mcp_error(exc.value)
    assert mcp_err is not None
    # -32003 is our CONFLICT code
    assert mcp_err.error.code == -32003


@pytest.mark.asyncio
async def test_update_module_requires_some_field(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    agent_id, key = register_agent(admin, name="t-upd-empty")
    page_id = home_page_id(admin)
    mod = _seed_agent_module(admin, agent_id, page_id)
    mcp = build_mcp_for_tests()
    with pytest.raises((McpError, ToolError)):
        await call_tool(
            mcp,
            "update_module",
            {"module_id": mod["id"]},
            agent_key=key,
        )
