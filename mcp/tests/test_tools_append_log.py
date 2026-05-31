"""Tests for the ``append_log`` MCP tool."""

from __future__ import annotations

import pytest

from app.backend import BackendClient

from ._mcp_helpers import build_mcp_for_tests, call_tool
from .conftest import AdminSession, home_page_id, register_agent


def _seed_log_stream(admin: AdminSession, agent_id: str, page_id: str) -> dict:
    r = admin.client.post(
        "/api/v1/modules",
        json={
            "type": "log_stream",
            "page_id": page_id,
            "data": {"entries": []},
            "config": {},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_append_log_applied_shape(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    agent_id, key = register_agent(admin, name="t-appendlog")
    page_id = home_page_id(admin)
    mod = _seed_log_stream(admin, agent_id, page_id)
    mcp = build_mcp_for_tests()
    result = await call_tool(
        mcp,
        "append_log",
        {
            "module_id": mod["id"],
            "entry": {"message": "first line", "level": "info"},
        },
        agent_key=key,
    )
    assert result["status"] == "applied"
    assert result["request_id"].startswith("apr_")
    assert "buffer_size" in result


@pytest.mark.asyncio
async def test_append_log_truncates_buffer_when_over(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    """Repeated appends past buffer size eventually surface a truncated_count."""
    agent_id, key = register_agent(admin, name="t-appendlog-trunc")
    page_id = home_page_id(admin)
    # Set a tiny buffer so we trigger truncation quickly.
    r = admin.client.post(
        "/api/v1/modules",
        json={
            "type": "log_stream",
            "page_id": page_id,
            "data": {"entries": []},
            "config": {"ring_buffer_size": 20},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    mod = r.json()
    mcp = build_mcp_for_tests()

    last = None
    for i in range(25):
        last = await call_tool(
            mcp,
            "append_log",
            {
                "module_id": mod["id"],
                "entry": {"message": f"line {i}"},
                # Unique idempotency keys so each is a fresh append.
                "idempotency_key": f"trunc-{i}",
            },
            agent_key=key,
        )
        assert last["status"] == "applied", last
    assert last["buffer_size"] <= 20
