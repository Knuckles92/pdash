"""Tests for the visibility + self-diagnosis MCP tools: whoami,
list_module_schemas, validate_module, module_health, render_page, get_module
(real endpoint), list_pages (real endpoint), and the screenshot_page guard.
"""

from __future__ import annotations

import pytest
from mcp import McpError
from mcp.server.fastmcp.exceptions import ToolError

from app.backend import BackendClient

from ._mcp_helpers import build_mcp_for_tests, call_tool, unwrap_mcp_error
from .conftest import AdminSession, home_page_id, register_agent


def _make_module(admin: AdminSession, page_id: str, owner_id: str, body: str = "hi") -> str:
    r = admin.client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "title": "m",
            "data": {"body": body},
            "config": {},
            "owner_kind": "agent",
            "owner_id": owner_id,
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_whoami(mcp_backend_client: BackendClient, admin: AdminSession) -> None:
    agent_id, key = register_agent(admin, name="who-tool")
    mcp = build_mcp_for_tests()
    result = await call_tool(mcp, "whoami", {}, agent_key=key)
    assert result["agent"]["id"] == agent_id
    assert result["agent"]["display_name"] == "who-tool"


@pytest.mark.asyncio
async def test_list_module_schemas(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="schemas-tool")
    mcp = build_mcp_for_tests()
    result = await call_tool(mcp, "list_module_schemas", {}, agent_key=key)
    assert "markdown" in result["types"]
    assert any(item["type"] == "markdown" for item in result["items"])


@pytest.mark.asyncio
async def test_validate_module_ok_and_errors(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="validate-tool")
    mcp = build_mcp_for_tests()

    ok = await call_tool(
        mcp, "validate_module", {"type": "markdown", "data": {"body": "hi"}}, agent_key=key
    )
    assert ok["ok"] is True

    bad = await call_tool(
        mcp, "validate_module", {"type": "markdown", "data": {}}, agent_key=key
    )
    assert bad["ok"] is False
    assert any(e["section"] == "data" for e in bad["errors"])


@pytest.mark.asyncio
async def test_module_health(mcp_backend_client: BackendClient, admin: AdminSession) -> None:
    agent_id, key = register_agent(admin, name="health-tool")
    page_id = home_page_id(admin)
    _make_module(admin, page_id, agent_id)
    mcp = build_mcp_for_tests()
    result = await call_tool(mcp, "module_health", {}, agent_key=key)
    assert result["items"]
    assert all("render_ok" in i for i in result["items"])


@pytest.mark.asyncio
async def test_render_page(mcp_backend_client: BackendClient, admin: AdminSession) -> None:
    agent_id, key = register_agent(admin, name="render-tool")
    page_id = home_page_id(admin)
    _make_module(admin, page_id, agent_id)
    mcp = build_mcp_for_tests()
    result = await call_tool(mcp, "render_page", {"page_id": page_id}, agent_key=key)
    assert result["page"]["slug"] == "home"
    assert isinstance(result["layout"]["ascii"], str) and result["layout"]["ascii"]


@pytest.mark.asyncio
async def test_get_module_real_endpoint(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    agent_id, key = register_agent(admin, name="getmod-tool")
    page_id = home_page_id(admin)
    mod_id = _make_module(admin, page_id, agent_id)
    mcp = build_mcp_for_tests()
    result = await call_tool(mcp, "get_module", {"module_id": mod_id}, agent_key=key)
    assert result["id"] == mod_id
    assert result["owned"] is True
    assert result["health"]["render_ok"] is True


@pytest.mark.asyncio
async def test_list_pages_real_endpoint(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="pages-tool")
    mcp = build_mcp_for_tests()
    result = await call_tool(mcp, "list_pages", {}, agent_key=key)
    assert any(p["slug"] == "home" for p in result["items"])


@pytest.mark.asyncio
async def test_screenshot_page_unavailable(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="shot-tool")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()
    # The live backend runs without PDASH_SCREENSHOT_SERVICE_URL, so the backend
    # returns 501 and the MCP layer surfaces a service_unavailable error.
    with pytest.raises((McpError, ToolError)) as exc:
        await call_tool(mcp, "screenshot_page", {"page_id": page_id}, agent_key=key)
    mcp_err = unwrap_mcp_error(exc.value)
    assert mcp_err is not None
    assert mcp_err.error.code == -32005  # SERVICE_UNAVAILABLE
