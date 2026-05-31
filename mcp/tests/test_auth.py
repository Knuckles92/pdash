"""Auth-layer tests for the MCP server.

Exercises :mod:`app.auth` against a real backend, validating:

- Unknown / malformed API keys return None / raise AuthError.
- A registered agent resolves correctly.
- Successful resolves are cached (no extra HTTP roundtrip within TTL).
"""

from __future__ import annotations

import pytest

from app import auth as auth_mod
from app.backend import BackendClient

from .conftest import AdminSession, register_agent


@pytest.mark.asyncio
async def test_bad_key_returns_none(mcp_backend_client: BackendClient, admin: AdminSession) -> None:
    register_agent(admin, name="auth-bad-real")
    info = await mcp_backend_client.resolve_key("hb_agt_bogus0000000000000000000000000")
    assert info is None


@pytest.mark.asyncio
async def test_bad_prefix_returns_none(mcp_backend_client: BackendClient, admin: AdminSession) -> None:
    register_agent(admin, name="auth-bad-prefix-real")
    info = await mcp_backend_client.resolve_key("totally-wrong")
    assert info is None


@pytest.mark.asyncio
async def test_good_key_resolves(mcp_backend_client: BackendClient, admin: AdminSession) -> None:
    agent_id, key = register_agent(admin, name="auth-good")
    info = await mcp_backend_client.resolve_key(key)
    assert info is not None
    assert info.agent_id == agent_id
    assert info.display_name == "auth-good"
    assert info.status == "active"


@pytest.mark.asyncio
async def test_resolve_from_token_caches(
    mcp_backend_client: BackendClient, admin: AdminSession, monkeypatch
) -> None:
    """Second call within TTL must NOT hit the backend."""
    _, key = register_agent(admin, name="auth-cache")
    auth_mod.clear_cache()

    # Warm
    info1 = await auth_mod.resolve_token(key)
    assert info1.display_name == "auth-cache"

    # Sabotage the backend client: any subsequent call would explode.
    calls = {"n": 0}
    orig = mcp_backend_client.resolve_key

    async def sabotaged(*a, **k):
        calls["n"] += 1
        return await orig(*a, **k)

    monkeypatch.setattr(mcp_backend_client, "resolve_key", sabotaged)

    info2 = await auth_mod.resolve_token(key)
    assert info2.agent_id == info1.agent_id
    assert calls["n"] == 0, "cache must avoid the second backend call"


@pytest.mark.asyncio
async def test_resolve_token_invalid_raises(
    mcp_backend_client: BackendClient, admin: AdminSession
) -> None:
    register_agent(admin, name="auth-raise")
    auth_mod.clear_cache()
    with pytest.raises(auth_mod.AuthError) as exc:
        await auth_mod.resolve_token("hb_agt_doesnotexist0000000000000")
    assert exc.value.code == "auth.invalid"


@pytest.mark.asyncio
async def test_extract_bearer_from_request() -> None:
    """Pure-unit: header extraction logic."""

    class FakeRequest:
        def __init__(self, headers: dict[str, str]) -> None:
            self.headers = headers

    assert auth_mod.extract_bearer(None) is None
    assert auth_mod.extract_bearer(FakeRequest({})) is None
    assert auth_mod.extract_bearer(FakeRequest({"authorization": "Bearer abc"})) == "abc"
    assert auth_mod.extract_bearer(FakeRequest({"Authorization": "bearer xyz"})) == "xyz"
    assert auth_mod.extract_bearer(FakeRequest({"authorization": "Basic foo"})) is None
