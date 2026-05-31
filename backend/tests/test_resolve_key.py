"""Tests for ``POST /api/v1/internal/auth/resolve-key``.

The MCP server uses this endpoint to translate a raw per-agent API key into
an agent_id (which it then sends as ``X-Agent-Id`` on every subsequent
internal call).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from _phase3_helpers import get_service_secret, register_agent


def _resolve(client: TestClient, secret: str, api_key: str):
    return client.post(
        "/api/v1/internal/auth/resolve-key",
        json={"api_key": api_key},
        headers={"Authorization": f"Bearer {secret}"},
    )


def test_resolve_key_happy_path(admin_client: TestClient) -> None:
    agent_id, api_key = register_agent(admin_client, name="resolve-happy")
    secret = get_service_secret()
    r = _resolve(admin_client, secret, api_key)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent_id"] == agent_id
    assert body["display_name"] == "resolve-happy"
    assert body["status"] == "active"
    assert "permissions" in body


def test_resolve_key_missing_service_secret_401(admin_client: TestClient) -> None:
    _, api_key = register_agent(admin_client, name="resolve-no-secret")
    r = admin_client.post(
        "/api/v1/internal/auth/resolve-key",
        json={"api_key": api_key},
    )
    assert r.status_code == 401
    assert r.json()["code"] == "auth.service_secret_missing"


def test_resolve_key_wrong_service_secret_401(admin_client: TestClient) -> None:
    _, api_key = register_agent(admin_client, name="resolve-wrong-secret")
    r = _resolve(admin_client, "not-the-secret", api_key)
    assert r.status_code == 401
    assert r.json()["code"] == "auth.service_secret_invalid"


def test_resolve_key_bad_prefix_401(admin_client: TestClient) -> None:
    secret = get_service_secret()
    r = _resolve(admin_client, secret, "not_a_real_key_prefix")
    assert r.status_code == 401
    assert r.json()["code"] == "auth.api_key_invalid"


def test_resolve_key_unknown_key_401(admin_client: TestClient) -> None:
    # Register a real agent so the active-agents scan has something to verify against.
    register_agent(admin_client, name="resolve-known")
    secret = get_service_secret()
    # Plausible-looking but wrong key.
    bogus = "hb_agt_" + "a" * 52
    r = _resolve(admin_client, secret, bogus)
    assert r.status_code == 401
    assert r.json()["code"] == "auth.api_key_invalid"


def test_resolve_key_disabled_agent_401(admin_client: TestClient) -> None:
    agent_id, api_key = register_agent(admin_client, name="resolve-disabled")
    admin_client.post(f"/api/v1/agents/{agent_id}/disable")
    secret = get_service_secret()
    r = _resolve(admin_client, secret, api_key)
    # Disabled agents are not "active" — they shouldn't resolve.
    assert r.status_code == 401
    assert r.json()["code"] == "auth.api_key_invalid"


def test_resolve_key_revoked_agent_401(admin_client: TestClient) -> None:
    agent_id, api_key = register_agent(admin_client, name="resolve-revoked")
    admin_client.delete(f"/api/v1/agents/{agent_id}")
    secret = get_service_secret()
    r = _resolve(admin_client, secret, api_key)
    assert r.status_code == 401
    assert r.json()["code"] == "auth.api_key_invalid"


def test_resolve_key_two_agents_pick_correct(admin_client: TestClient) -> None:
    """Verification scan must return the right agent when multiple are active."""
    a1_id, k1 = register_agent(admin_client, name="resolve-multi-a")
    a2_id, k2 = register_agent(admin_client, name="resolve-multi-b")
    secret = get_service_secret()
    r1 = _resolve(admin_client, secret, k1)
    r2 = _resolve(admin_client, secret, k2)
    assert r1.json()["agent_id"] == a1_id
    assert r2.json()["agent_id"] == a2_id


def test_resolve_key_bumps_last_active_at(admin_client: TestClient) -> None:
    agent_id, api_key = register_agent(admin_client, name="resolve-bumps-last")
    secret = get_service_secret()
    r = _resolve(admin_client, secret, api_key)
    assert r.status_code == 200
    # Fetch the agent and confirm last_active_at populated.
    g = admin_client.get(f"/api/v1/agents/{agent_id}")
    assert g.status_code == 200
    assert g.json()["last_active_at"] is not None
