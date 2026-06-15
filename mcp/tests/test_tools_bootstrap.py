"""Ungated onboarding tools: onboarding, request_registration, claim_registration.

End-to-end against the live backend: a keyless client requests registration, the
admin approves over HTTP, and the client claims its minted key — which then works
on a gated tool.
"""

from __future__ import annotations

import pytest
from mcp import McpError
from mcp.server.fastmcp.exceptions import ToolError

from app.backend import BackendClient

from ._mcp_helpers import build_mcp_for_tests, call_tool, unwrap_mcp_error
from .conftest import AdminSession


@pytest.mark.asyncio
async def test_onboarding_needs_no_key(mcp_backend_client: BackendClient) -> None:
    mcp = build_mcp_for_tests()
    result = await call_tool(mcp, "onboarding", {}, agent_key=None)
    assert isinstance(result, dict)
    assert result["steps"]
    assert "auth_model" in result


@pytest.mark.asyncio
async def test_request_approve_claim_flow(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    mcp = build_mcp_for_tests()

    reg = await call_tool(
        mcp,
        "request_registration",
        {"display_name": "mcp-onboard-bot", "rationale": "publish status modules"},
        agent_key=None,
    )
    assert reg["status"] == "pending"
    assert reg["claim_token"].startswith("hb_reg_")
    rid = reg["registration_id"]

    pending = await call_tool(
        mcp, "claim_registration", {"claim_token": reg["claim_token"]}, agent_key=None
    )
    assert pending["status"] == "pending"

    listing = admin.client.get(
        "/api/v1/approval-requests",
        params={"status": "pending", "action_type": "register_agent"},
    )
    assert listing.status_code == 200, listing.text
    apr_id = next(
        item["id"]
        for item in listing.json()["items"]
        if item.get("target_id") == rid
    )

    appr = admin.client.post(f"/api/v1/approval-requests/{apr_id}/approve", json={})
    assert appr.status_code == 200, appr.text
    assert appr.json()["applied"] is True

    claimed = await call_tool(
        mcp, "claim_registration", {"claim_token": reg["claim_token"]}, agent_key=None
    )
    assert claimed["status"] == "approved"
    assert claimed["api_key"].startswith("hb_agt_")

    # The freshly minted key works on a normal gated tool.
    who = await call_tool(mcp, "whoami", {}, agent_key=claimed["api_key"])
    assert who["agent"]["display_name"] == "mcp-onboard-bot"


@pytest.mark.asyncio
async def test_request_registration_name_conflict(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    admin.client.post("/api/v1/agents", json={"display_name": "taken-bot"})
    mcp = build_mcp_for_tests()
    with pytest.raises((McpError, ToolError)) as exc:
        await call_tool(
            mcp, "request_registration", {"display_name": "taken-bot"}, agent_key=None
        )
    err = unwrap_mcp_error(exc.value)
    assert err is not None
    assert err.error.code == -32003  # _CONFLICT


@pytest.mark.asyncio
async def test_claim_unknown_token(mcp_backend_client: BackendClient) -> None:
    mcp = build_mcp_for_tests()
    with pytest.raises((McpError, ToolError)) as exc:
        await call_tool(
            mcp, "claim_registration", {"claim_token": "hb_reg_nope"}, agent_key=None
        )
    err = unwrap_mcp_error(exc.value)
    assert err is not None
    assert err.error.code == -32002  # _NOT_FOUND
