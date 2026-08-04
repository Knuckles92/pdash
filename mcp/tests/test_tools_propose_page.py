"""End-to-end tests for the ``propose_page`` MCP tool (type passthrough)."""

from __future__ import annotations

import pytest

from app.backend import BackendClient

from ._mcp_helpers import build_mcp_for_tests, call_tool
from .conftest import AdminSession, register_agent


def _request_payload(admin: AdminSession, request_id: str) -> dict:
    detail = admin.client.get(f"/api/v1/approval-requests/{request_id}")
    assert detail.status_code == 200, detail.text
    return detail.json()["proposed_payload"]


@pytest.mark.asyncio
async def test_propose_page_default_type_agent(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="t-page-default")
    mcp = build_mcp_for_tests()
    result = await call_tool(
        mcp,
        "propose_page",
        {"name": "Workspace", "slug": "t-ws-default"},
        agent_key=key,
    )
    assert result["status"] == "pending"
    assert _request_payload(admin, result["request_id"])["type"] == "agent"


@pytest.mark.asyncio
async def test_propose_page_canvas_type_passthrough(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="t-page-canvas")
    mcp = build_mcp_for_tests()
    result = await call_tool(
        mcp,
        "propose_page",
        {"name": "Status Board", "slug": "t-ws-canvas", "type": "canvas"},
        agent_key=key,
    )
    assert result["status"] == "pending"
    assert _request_payload(admin, result["request_id"])["type"] == "canvas"


@pytest.mark.asyncio
async def test_propose_page_rejects_other_types(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="t-page-badtype")
    mcp = build_mcp_for_tests()
    with pytest.raises(Exception):
        await call_tool(
            mcp,
            "propose_page",
            {"name": "Sneaky", "slug": "t-ws-sneaky", "type": "corkboard"},
            agent_key=key,
        )
