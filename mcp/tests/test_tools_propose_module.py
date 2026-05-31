"""End-to-end tests for the ``propose_module`` MCP tool."""

from __future__ import annotations

import pytest

from app.backend import BackendClient

from ._mcp_helpers import build_mcp_for_tests, call_tool
from .conftest import AdminSession, home_page_id, register_agent


@pytest.mark.asyncio
async def test_propose_module_routes_to_pending(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="t-propose-pending")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()
    result = await call_tool(
        mcp,
        "propose_module",
        {
            "page_id": page_id,
            "type": "markdown",
            "title": "first",
            "data": {"body": "# hello"},
            "config": {},
        },
        agent_key=key,
    )
    assert result["status"] == "pending"
    assert result["request_id"].startswith("apr_")
    assert result.get("expires_at")


@pytest.mark.asyncio
async def test_propose_module_applied_after_rule(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    agent_id, key = register_agent(admin, name="t-propose-apply")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()

    # First call -> pending.
    r1 = await call_tool(
        mcp,
        "propose_module",
        {
            "page_id": page_id,
            "type": "markdown",
            "data": {"body": "# v1"},
            "config": {},
        },
        agent_key=key,
    )
    assert r1["status"] == "pending"
    req_id = r1["request_id"]

    # Admin approves + creates a narrow rule.
    approve = admin.client.post(
        f"/api/v1/approval-requests/{req_id}/approve",
        json={
            "reason": "ok",
            "create_rule": {
                "agent_id": agent_id,
                "action_type": "create_module",
                "module_type": "markdown",
                "outcome": "auto_approve",
                "priority": 50,
            },
        },
    )
    assert approve.status_code == 200, approve.text

    # Second call -> auto-applied via rule.
    r2 = await call_tool(
        mcp,
        "propose_module",
        {
            "page_id": page_id,
            "type": "markdown",
            "data": {"body": "# v2"},
            "config": {
                "appearance": {
                    "theme": "outline",
                    "color": "cyan",
                },
            },
        },
        agent_key=key,
    )
    assert r2["status"] == "applied", r2
    assert "module" in r2
    assert r2["module"]["data"]["body"] == "# v2"
    assert r2["module"]["config"]["appearance"] == {
        "theme": "outline",
        "color": "cyan",
    }


@pytest.mark.asyncio
async def test_propose_module_auto_idempotency_key_dedupes(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    """When the agent doesn't pass idempotency_key, the MCP server auto-mints
    one and dedupes rapid retries with identical args."""
    _, key = register_agent(admin, name="t-propose-idem-auto")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()
    args = {
        "page_id": page_id,
        "type": "markdown",
        "data": {"body": "# idem"},
        "config": {},
    }
    r1 = await call_tool(mcp, "propose_module", args, agent_key=key)
    r2 = await call_tool(mcp, "propose_module", dict(args), agent_key=key)
    assert r1["status"] == "pending"
    assert r2["status"] == "pending"
    assert r2["request_id"] == r1["request_id"], "auto-idem key should dedupe identical args"


@pytest.mark.asyncio
async def test_propose_module_denied_envelope(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    """A deny rule produces a payload-level ``status: denied`` (NOT an MCP error)."""
    agent_id, key = register_agent(admin, name="t-propose-deny")
    page_id = home_page_id(admin)

    # Install a deny rule for this agent's create_module + markdown.
    rule = admin.client.post(
        "/api/v1/approval-rules",
        json={
            "agent_id": agent_id,
            "action_type": "create_module",
            "module_type": "markdown",
            "outcome": "deny",
            "priority": 10,
        },
    )
    assert rule.status_code == 201, rule.text

    mcp = build_mcp_for_tests()
    result = await call_tool(
        mcp,
        "propose_module",
        {
            "page_id": page_id,
            "type": "markdown",
            "data": {"body": "# denied"},
            "config": {},
        },
        agent_key=key,
    )
    assert result["status"] == "denied"
    assert result.get("reason")
    assert result.get("rule_id")
