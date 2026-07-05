"""Tests for the mcp_tool action_target dispatcher.

These tests mock the `mcp` SDK at the import site so we don't need a live
MCP server. They verify:

- auth header propagation (bearer secret resolved via `kv_settings`)
- payload arguments are forwarded to `call_tool`
- failures captured as `execution_result.ok=False` with an error message
"""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    internal_headers,
    register_agent,
)


# ---------------------------------------------------------------------------
# Fake mcp SDK plumbed into apply.py via sys.modules
# ---------------------------------------------------------------------------


class _FakeContentBlock:
    def __init__(self, text: str) -> None:
        self.text = text

    def model_dump(self) -> dict[str, str]:
        return {"text": self.text}


class _FakeCallToolResult:
    def __init__(self, *, content: list[Any], is_error: bool = False) -> None:
        self.content = content
        self.isError = is_error


class _FakeClientSession:
    """Tracks initialize / call_tool invocations on a captured `_LAST` slot."""

    LAST: dict[str, Any] = {}

    def __init__(self, read_stream: Any, write_stream: Any) -> None:
        self._read = read_stream
        self._write = write_stream

    async def __aenter__(self) -> "_FakeClientSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def initialize(self) -> None:
        _FakeClientSession.LAST["initialized"] = True

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None):
        _FakeClientSession.LAST["call_tool"] = {"name": name, "arguments": arguments}
        # Return a stub success result unless arguments contain `_fail`.
        if (arguments or {}).get("_fail"):
            return _FakeCallToolResult(
                content=[_FakeContentBlock("nope")], is_error=True
            )
        return _FakeCallToolResult(content=[_FakeContentBlock(f"ran:{name}")])


class _FakeStreamHttpCtx:
    def __init__(self, url: str, headers: dict[str, str] | None, timeout: timedelta) -> None:
        _FakeClientSession.LAST["url"] = url
        _FakeClientSession.LAST["headers"] = dict(headers or {})
        _FakeClientSession.LAST["timeout"] = timeout

    async def __aenter__(self):
        return (object(), object(), None)

    async def __aexit__(self, *exc_info):
        return None


def _streamablehttp_client(url: str, headers: dict[str, str] | None = None, timeout: timedelta | None = None, **_kw: Any) -> Any:
    return _FakeStreamHttpCtx(url, headers, timeout or timedelta(seconds=30))


@pytest.fixture(autouse=True)
def _install_fake_mcp(monkeypatch: pytest.MonkeyPatch):
    _FakeClientSession.LAST.clear()
    mcp_mod = types.ModuleType("mcp")
    mcp_mod.ClientSession = _FakeClientSession  # type: ignore[attr-defined]
    client_mod = types.ModuleType("mcp.client")
    streamable_mod = types.ModuleType("mcp.client.streamable_http")
    streamable_mod.streamablehttp_client = _streamablehttp_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mcp", mcp_mod)
    monkeypatch.setitem(sys.modules, "mcp.client", client_mod)
    monkeypatch.setitem(sys.modules, "mcp.client.streamable_http", streamable_mod)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _store_secret(target_id: str, field: str, value: str) -> None:
    from app.approval.apply import secret_kv_key
    from app.auth.secrets import set_kv
    from app.db import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as session:
        await set_kv(session, secret_kv_key(target_id, field), value)
        await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_mcp_tool_dispatch_propagates_bearer_and_returns_ok(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="mcp-tool-test-1")
    secret = get_service_secret()

    target = admin_client.post(
        "/api/v1/action-targets",
        json={
            "name": "ha-toggle",
            "kind": "mcp_tool",
            "config": {
                "url": "https://ha.lan/mcp",
                "tool_name": "homeassistant.toggle",
                "auth": {"kind": "bearer", "secret_ref": "main"},
            },
            "mode": "sync",
        },
    )
    assert target.status_code == 201, target.text
    tid = target.json()["id"]

    # Stash the secret in kv_settings under the target's namespace.
    asyncio.run(_store_secret(tid, "main", "s3kret-token"))

    resp = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid, "payload": {"entity": "light.kitchen"}},
        headers=internal_headers(agent_id, secret, idempotency_key="mt-ok"),
    )
    assert resp.status_code == 202
    req_id = resp.json()["request_id"]

    # Approve to fire.
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={}
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["applied"] is True

    detail = admin_client.get(f"/api/v1/approval-requests/{req_id}").json()
    assert detail["status"] == "applied"
    er = detail["execution_result"]
    assert er["ok"] is True
    assert er["tool_name"] == "homeassistant.toggle"

    # The fake captured the auth header and tool name.
    last = _FakeClientSession.LAST
    assert last["url"] == "https://ha.lan/mcp"
    assert last["headers"].get("Authorization") == "Bearer s3kret-token"
    assert last["call_tool"]["name"] == "homeassistant.toggle"
    assert last["call_tool"]["arguments"] == {"entity": "light.kitchen"}


def test_mcp_tool_dispatch_captures_call_tool_isError(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="mcp-tool-test-2")
    secret = get_service_secret()
    target = admin_client.post(
        "/api/v1/action-targets",
        json={
            "name": "ha-fail",
            "kind": "mcp_tool",
            "config": {
                "url": "https://ha.lan/mcp",
                "tool_name": "homeassistant.boom",
                "auth": None,
            },
            "mode": "sync",
        },
    )
    tid = target.json()["id"]

    resp = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid, "payload": {"_fail": True}},
        headers=internal_headers(agent_id, secret, idempotency_key="mt-bad"),
    )
    req_id = resp.json()["request_id"]
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={}
    )
    assert approve.status_code == 200
    detail = admin_client.get(f"/api/v1/approval-requests/{req_id}").json()
    er = detail["execution_result"]
    assert er["ok"] is False
    # No auth header should have been sent when auth is None.
    assert _FakeClientSession.LAST["headers"].get("Authorization") is None


def test_mcp_tool_dispatch_missing_config_returns_failure(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="mcp-tool-test-3")
    secret = get_service_secret()
    # Missing url
    target = admin_client.post(
        "/api/v1/action-targets",
        json={
            "name": "ha-bad",
            "kind": "mcp_tool",
            "config": {"tool_name": "homeassistant.toggle"},
            "mode": "sync",
        },
    )
    tid = target.json()["id"]
    resp = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid},
        headers=internal_headers(agent_id, secret, idempotency_key="mt-miss"),
    )
    req_id = resp.json()["request_id"]
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={}
    )
    assert approve.status_code == 200
    detail = admin_client.get(f"/api/v1/approval-requests/{req_id}").json()
    er = detail["execution_result"]
    assert er["ok"] is False
    assert "missing url" in (er.get("error") or "").lower()
