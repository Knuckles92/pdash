"""The custom HTTP routes added in app.health: /healthz and /info."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from app.settings import reset_settings_cache

SECRET = "test-service-secret"


@pytest.fixture
def mcp_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastMCP]:
    monkeypatch.setenv("PDASH_SERVICE_SECRET", SECRET)
    reset_settings_cache()
    # Import after env is set so build_server sees the secret.
    from app.main import build_server

    yield build_server()
    reset_settings_cache()


async def _receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _request(path: str, *, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "root_path": "",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "headers": raw_headers,
            "query_string": b"",
        },
        receive=_receive,
    )


def _route(mcp: FastMCP, path: str) -> Route:
    for route in mcp._custom_starlette_routes:  # noqa: SLF001
        if isinstance(route, Route) and route.path == path:
            return route
    raise AssertionError(f"route not found: {path}")


async def _call(mcp: FastMCP, path: str, *, headers: dict[str, str] | None = None) -> Response:
    route = _route(mcp, path)
    return await route.endpoint(_request(path, headers=headers))


@pytest.mark.asyncio
async def test_healthz_is_open(mcp_server: FastMCP) -> None:
    resp = await _call(mcp_server, "/healthz")
    assert resp.status_code == 200
    assert json.loads(resp.body) == {"status": "ok"}


@pytest.mark.asyncio
async def test_skill_file_is_open_and_points_at_mcp(mcp_server: FastMCP) -> None:
    resp = await _call(mcp_server, "/mcp-skill/SKILL.md")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
    assert resp.headers["access-control-allow-origin"] == "*"

    body = resp.body.decode()
    assert body.startswith("---\n")
    assert "name: pdash-onboarding" in body
    assert "description: Connect to pdash" in body
    assert '"url": "http://testserver/mcp"' in body
    assert "Do not call the\nMCP endpoint with raw curl, WebFetch" in body
    assert "Do not call `request_registration` again while waiting." in body
    assert "Never retry a write that returned `pending`" in body


@pytest.mark.asyncio
async def test_info_requires_bearer(mcp_server: FastMCP) -> None:
    assert (await _call(mcp_server, "/info")).status_code == 401
    assert (
        await _call(mcp_server, "/info", headers={"Authorization": "Bearer wrong"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_info_returns_version_and_categorized_tools(mcp_server: FastMCP) -> None:
    resp = await _call(mcp_server, "/info", headers={"Authorization": f"Bearer {SECRET}"})
    assert resp.status_code == 200
    body = json.loads(resp.body)

    assert body["name"] == "pdash"
    assert body["version"]
    assert isinstance(body["tools"], list) and body["tools"]

    by_name = {t["name"]: t["category"] for t in body["tools"]}
    # Spot-check one write tool and one read tool.
    assert by_name["propose_module"] == "write"
    assert by_name["whoami"] == "read"
    # Write tools are listed before read tools.
    categories = [t["category"] for t in body["tools"]]
    assert categories == sorted(categories, key=lambda c: c != "write")
