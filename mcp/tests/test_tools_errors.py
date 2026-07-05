"""Error-translation tests: backend errors → MCP errors with the right codes.

FastMCP wraps every tool-internal exception in a ``ToolError``. The
underlying :class:`McpError` (with our domain code + data) is the
``__cause__``. ``unwrap_mcp_error`` digs it out.
"""

from __future__ import annotations

import httpx
import pytest
from mcp import McpError
from mcp.server.fastmcp.exceptions import ToolError

from app import backend as backend_mod
from app.backend import BackendClient, BackendError

from ._mcp_helpers import build_mcp_for_tests, call_tool, unwrap_mcp_error
from .conftest import AdminSession, home_page_id, register_agent


# Error codes mirror the constants in app.tools
_AUTH_REQUIRED = -32001
_NOT_FOUND = -32002
_CONFLICT = -32003
_RATE_LIMIT = -32004
_SERVICE_UNAVAILABLE = -32005
_AGENT_DISABLED = -32006


def _err_code(exc: BaseException) -> int:
    mcp_err = unwrap_mcp_error(exc)
    if mcp_err is None:
        return 0
    err = mcp_err.error if hasattr(mcp_err, "error") else None
    return err.code if err else getattr(mcp_err, "code", 0)


@pytest.mark.asyncio
async def test_missing_auth_header(mcp_backend_client: BackendClient, admin: AdminSession) -> None:
    register_agent(admin, name="t-err-noauth")
    mcp = build_mcp_for_tests()
    with pytest.raises((McpError, ToolError)) as exc:
        await call_tool(mcp, "get_module_schema", {"type": "markdown"}, agent_key=None)  # type: ignore[arg-type]
    assert _err_code(exc.value) == _AUTH_REQUIRED


@pytest.mark.asyncio
async def test_bad_auth_token(mcp_backend_client: BackendClient, admin: AdminSession) -> None:
    register_agent(admin, name="t-err-badauth")
    mcp = build_mcp_for_tests()
    with pytest.raises((McpError, ToolError)) as exc:
        await call_tool(
            mcp,
            "get_module_schema",
            {"type": "markdown"},
            agent_key="hb_agt_doesnotexist0000000",
        )
    assert _err_code(exc.value) == _AUTH_REQUIRED


@pytest.mark.asyncio
async def test_agent_disabled_after_resolve(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    """If an agent's key resolves but the agent is then disabled, subsequent
    internal calls return ``agent.disabled`` (mapped to MCP _AGENT_DISABLED).

    We bypass auth cache by clearing it; the agent gets disabled between
    resolve and the call to a write tool."""
    from app import auth as auth_mod
    agent_id, key = register_agent(admin, name="t-err-disabled")
    auth_mod.clear_cache()
    # First, resolve once (caches).
    info = await auth_mod.resolve_token(key)
    assert info.agent_id == agent_id
    # Disable the agent.
    r = admin.client.post(f"/api/v1/agents/{agent_id}/disable")
    assert r.status_code == 200
    # Now any internal call (which sets X-Agent-Id) will see agent.disabled.
    mcp = build_mcp_for_tests()
    with pytest.raises((McpError, ToolError)) as exc:
        await call_tool(mcp, "get_module_schema", {"type": "markdown"}, agent_key=key)
    assert _err_code(exc.value) == _AGENT_DISABLED


@pytest.mark.asyncio
async def test_service_unavailable(monkeypatch) -> None:
    """Network/transport failure surfaces as _SERVICE_UNAVAILABLE."""
    from app import auth as auth_mod
    auth_mod.clear_cache()
    # Build a backend client pointed at an unreachable URL.
    bad = BackendClient(base_url="http://127.0.0.1:1", service_secret="x")
    backend_mod.set_client_for_tests(bad)
    try:
        mcp = build_mcp_for_tests()
        # Auth resolution itself will fail because the backend is unreachable.
        with pytest.raises((McpError, ToolError)) as exc:
            await call_tool(
                mcp,
                "get_module_schema",
                {"type": "markdown"},
                agent_key="hb_agt_anything0000000000000000",
            )
        assert _err_code(exc.value) in (_SERVICE_UNAVAILABLE, _AUTH_REQUIRED)
    finally:
        await bad.aclose()
        backend_mod.set_client_for_tests(None)


@pytest.mark.asyncio
async def test_rate_limit_with_retry_after(
    mcp_backend_client: BackendClient, admin: AdminSession, monkeypatch
) -> None:
    """Patch the backend client to simulate a 429 + Retry-After response.

    We do this with httpx.MockTransport because the real backend's token
    bucket is generous and would require thousands of calls to trip."""
    register_agent(admin, name="t-err-429")

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/resolve-key"):
            return httpx.Response(
                200,
                json={
                    "agent_id": "agt_fake",
                    "display_name": "fake",
                    "status": "active",
                    "permissions": {},
                },
            )
        return httpx.Response(
            429,
            json={
                "code": "rate_limit.exceeded",
                "title": "Too Many Requests",
                "detail": "Rate limit exceeded; retry in 2s",
                "status": 429,
                "retry_after_ms": 2000,
            },
            headers={"Retry-After": "2"},
        )

    transport = httpx.MockTransport(_handler)
    client = BackendClient(base_url="http://mock", service_secret="x")
    # Swap the underlying httpx client to use our transport.
    await client._client.aclose()  # noqa: SLF001
    client._client = httpx.AsyncClient(  # noqa: SLF001
        base_url="http://mock", transport=transport, timeout=5.0,
    )
    backend_mod.set_client_for_tests(client)
    try:
        from app import auth as auth_mod
        auth_mod.clear_cache()
        mcp = build_mcp_for_tests()
        with pytest.raises((McpError, ToolError)) as exc:
            await call_tool(
                mcp,
                "get_module_schema",
                {"type": "markdown"},
                agent_key="hb_agt_whatever000000000000",
            )
        mcp_err = unwrap_mcp_error(exc.value)
        assert mcp_err is not None
        err = mcp_err.error
        assert err.code == _RATE_LIMIT
        assert err.data and err.data.get("retry_after_ms") == 2000
    finally:
        await client.aclose()
        backend_mod.set_client_for_tests(None)
