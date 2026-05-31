"""Agent CRUD + key rotation tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_agent_returns_plaintext_key_once(admin_client: TestClient) -> None:
    resp = admin_client.post(
        "/api/v1/agents",
        json={"display_name": "claude-code", "description": "dev agent"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["agent"]["id"].startswith("agt_")
    assert body["agent"]["display_name"] == "claude-code"
    assert body["agent"]["status"] == "active"
    assert body["api_key"].startswith("hb_agt_")

    # GET should NOT include the plaintext key
    resp = admin_client.get(f"/api/v1/agents/{body['agent']['id']}")
    assert resp.status_code == 200
    fetched = resp.json()
    assert "api_key" not in fetched


def test_rotate_key_returns_new_key(admin_client: TestClient) -> None:
    resp = admin_client.post(
        "/api/v1/agents", json={"display_name": "agent-1"}
    )
    aid = resp.json()["agent"]["id"]
    first_key = resp.json()["api_key"]

    resp = admin_client.post(f"/api/v1/agents/{aid}/rotate-key")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["api_key"].startswith("hb_agt_")
    assert body["api_key"] != first_key


def test_disable_enable_agent(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/agents", json={"display_name": "agent-2"})
    aid = resp.json()["agent"]["id"]

    resp = admin_client.post(f"/api/v1/agents/{aid}/disable")
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    resp = admin_client.post(f"/api/v1/agents/{aid}/enable")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_revoke_via_delete(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/agents", json={"display_name": "agent-3"})
    aid = resp.json()["agent"]["id"]

    resp = admin_client.delete(f"/api/v1/agents/{aid}")
    assert resp.status_code in (204, 200)

    # GET should still find them with status=revoked.
    resp = admin_client.get(f"/api/v1/agents/{aid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"

    # Cannot rotate key on revoked
    resp = admin_client.post(f"/api/v1/agents/{aid}/rotate-key")
    assert resp.status_code == 400
    assert resp.json()["code"] == "agent.revoked"


def test_duplicate_display_name_conflicts(admin_client: TestClient) -> None:
    admin_client.post("/api/v1/agents", json={"display_name": "dup"})
    resp = admin_client.post("/api/v1/agents", json={"display_name": "dup"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "agent.name_taken"
