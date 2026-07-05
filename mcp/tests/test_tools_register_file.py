"""End-to-end MCP tests for the file-drop tools against a live backend.

Mirrors test_tools_propose_module.py: the backend runs in a subprocess on the
same host, so the test writes a file into the inbox dir the dropbox tool reports
and then registers it through the MCP surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ._mcp_helpers import build_mcp_for_tests, call_tool, unwrap_mcp_error
from .conftest import AdminSession, home_page_id, register_agent

# JSON-RPC invalid-params code used by the tool layer for backend 400s.
_INVALID_PARAMS = -32602


async def _dropbox_target(mcp, key: str, page_id: str) -> Path:
    resp = await call_tool(mcp, "get_file_dropbox", {"page_id": page_id}, agent_key=key)
    assert resp["target"], resp
    return Path(resp["target"])


@pytest.mark.asyncio
async def test_get_file_dropbox_returns_target(
    mcp_backend_client, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="mcp-dropbox")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()
    resp = await call_tool(mcp, "get_file_dropbox", {"page_id": page_id}, agent_key=key)
    assert resp["inbox_root"]
    assert page_id in resp["target"]
    assert resp["max_bytes"] > 0
    assert Path(resp["target"]).is_dir()


@pytest.mark.asyncio
async def test_register_pending_then_approve(
    mcp_backend_client, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="mcp-reg")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()
    target = await _dropbox_target(mcp, key, page_id)
    (target / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\nx")

    r1 = await call_tool(
        mcp,
        "register_file",
        {"inbox_name": "chart.png", "display_name": "Chart", "page_id": page_id},
        agent_key=key,
    )
    assert r1["status"] == "pending", r1
    req_id = r1["request_id"]

    approve = admin.client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={"reason": "ok"}
    )
    assert approve.status_code == 200, approve.text
    file_id = approve.json()["apply_result"]["file_id"]
    assert file_id.startswith("fil_")


@pytest.mark.asyncio
async def test_register_auto_applies_after_rule(
    mcp_backend_client, admin: AdminSession
) -> None:
    agent_id, key = register_agent(admin, name="mcp-reg-auto")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()
    target = await _dropbox_target(mcp, key, page_id)
    (target / "a.png").write_bytes(b"a")

    r1 = await call_tool(
        mcp,
        "register_file",
        {"inbox_name": "a.png", "display_name": "A", "page_id": page_id},
        agent_key=key,
    )
    assert r1["status"] == "pending"
    admin.client.post(
        f"/api/v1/approval-requests/{r1['request_id']}/approve",
        json={
            "reason": "auto",
            "create_rule": {
                "agent_id": agent_id,
                "action_type": "register_file",
                "outcome": "auto_approve",
                "priority": 50,
            },
        },
    )

    (target / "b.png").write_bytes(b"b")
    r2 = await call_tool(
        mcp,
        "register_file",
        {"inbox_name": "b.png", "display_name": "B", "page_id": page_id},
        agent_key=key,
    )
    assert r2["status"] == "applied", r2
    assert r2["file_id"].startswith("fil_")
    assert r2["url"].endswith("/raw")


@pytest.mark.asyncio
async def test_register_denied_is_payload_level(
    mcp_backend_client, admin: AdminSession
) -> None:
    agent_id, key = register_agent(admin, name="mcp-reg-deny")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()
    target = await _dropbox_target(mcp, key, page_id)
    (target / "d.png").write_bytes(b"d")

    # A deny rule makes register_file return status="denied" (not an MCP error).
    admin.client.post(
        "/api/v1/approval-rules",
        json={
            "agent_id": agent_id,
            "action_type": "register_file",
            "outcome": "deny",
            "priority": 10,
        },
    )
    r = await call_tool(
        mcp,
        "register_file",
        {"inbox_name": "d.png", "display_name": "D", "page_id": page_id},
        agent_key=key,
    )
    assert r["status"] == "denied", r
    assert "reason" in r


@pytest.mark.asyncio
async def test_register_traversal_is_invalid_params(
    mcp_backend_client, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="mcp-reg-trav")
    page_id = home_page_id(admin)
    mcp = build_mcp_for_tests()
    with pytest.raises(Exception) as ei:  # noqa: PT011 — we unwrap below
        await call_tool(
            mcp,
            "register_file",
            {"inbox_name": "../escape.png", "display_name": "X", "page_id": page_id},
            agent_key=key,
        )
    mcp_err = unwrap_mcp_error(ei.value)
    assert mcp_err is not None
    assert mcp_err.error.code == _INVALID_PARAMS


@pytest.mark.asyncio
async def test_register_rejects_unknown_arg(
    mcp_backend_client, admin: AdminSession
) -> None:
    _, key = register_agent(admin, name="mcp-reg-extra")
    mcp = build_mcp_for_tests()
    with pytest.raises(Exception):
        await call_tool(
            mcp,
            "register_file",
            {"inbox_name": "x.png", "display_name": "X", "bogus": 1},
            agent_key=key,
        )
