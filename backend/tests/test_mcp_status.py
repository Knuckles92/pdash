"""MCP control center status endpoint (GET /api/v1/mcp/status)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import mcp_status as mcp_status_mod


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Stand-in for httpx.AsyncClient as an async context manager."""

    def __init__(self, *, get_result):
        self._get_result = get_result

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_exc) -> None:
        return None

    async def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
        if isinstance(self._get_result, Exception):
            raise self._get_result
        return self._get_result


def _patch_client(monkeypatch: pytest.MonkeyPatch, get_result) -> None:
    def factory(*_args, **_kwargs):
        return _FakeClient(get_result=get_result)

    monkeypatch.setattr(mcp_status_mod.httpx, "AsyncClient", factory)


def test_status_requires_session(client: TestClient) -> None:
    assert client.get("/api/v1/mcp/status").status_code == 401


def test_status_reachable(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    info = {
        "name": "pdash",
        "version": "1.2.3",
        "sse_connected": True,
        "auth_cache_ttl_s": 30.0,
        "idem_dedupe_ttl_s": 60.0,
        "tools": [
            {"name": "propose_module", "description": "create", "category": "write"},
            {"name": "whoami", "description": "id", "category": "read"},
        ],
    }
    _patch_client(monkeypatch, _FakeResponse(200, info))

    resp = admin_client.get("/api/v1/mcp/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert body["error"] is None
    assert body["mcp_version"] == "1.2.3"
    assert body["sse_connected"] is True
    assert body["service_secret_configured"] is True
    assert {t["name"] for t in body["tools"]} == {"propose_module", "whoami"}
    cats = {t["name"]: t["category"] for t in body["tools"]}
    assert cats["propose_module"] == "write"
    assert cats["whoami"] == "read"


def test_status_unreachable_does_not_raise(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, httpx.ConnectError("refused"))

    resp = admin_client.get("/api/v1/mcp/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is False
    assert body["error"]
    assert body["tools"] == []
    # Backend-side facts are still reported even when MCP is down.
    assert body["backend_version"]
    assert body["service_secret_configured"] is True
