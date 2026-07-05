"""End-to-end tests for the ``propose_page`` MCP tool (kind passthrough)."""

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
async def test_propose_page_default_kind_agent(
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
    assert _request_payload(admin, result["request_id"])["kind"] == "agent"


@pytest.mark.asyncio
async def test_propose_page_canvas_kind_passthrough(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="t-page-canvas")
    mcp = build_mcp_for_tests()
    result = await call_tool(
        mcp,
        "propose_page",
        {"name": "Status Board", "slug": "t-ws-canvas", "kind": "canvas"},
        agent_key=key,
    )
    assert result["status"] == "pending"
    assert _request_payload(admin, result["request_id"])["kind"] == "canvas"


@pytest.mark.asyncio
async def test_propose_page_rejects_other_kinds(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="t-page-badkind")
    mcp = build_mcp_for_tests()
    with pytest.raises(Exception):
        await call_tool(
            mcp,
            "propose_page",
            {"name": "Sneaky", "slug": "t-ws-sneaky", "kind": "corkboard"},
            agent_key=key,
        )
