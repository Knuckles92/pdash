"""Agent self-registration (agent-first MCP onboarding).

Covers the ungated bootstrap surface (service-secret only) + the Approvals inbox
for admin review, and the end-to-end mint-on-claim flow.
"""

from __future__ import annotations

from _phase3_helpers import get_service_secret
from fastapi.testclient import TestClient

REG = "/api/v1/internal/bootstrap/register"
CLAIM = "/api/v1/internal/bootstrap/claim"


def _secret_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_service_secret()}"}


def _register(admin_client: TestClient, display_name: str, **extra: object) -> dict:
    body = {"display_name": display_name, **extra}
    r = admin_client.post(REG, json=body, headers=_secret_headers())
    assert r.status_code == 201, r.text
    return r.json()


def _pending_approval_id(admin_client: TestClient, registration_id: str) -> str:
    listing = admin_client.get(
        "/api/v1/approval-requests",
        params={"status": "pending", "action_type": "register_agent"},
    )
    assert listing.status_code == 200, listing.text
    for item in listing.json()["items"]:
        if item.get("target_id") == registration_id:
            return item["id"]
    raise AssertionError(f"no pending approval for registration {registration_id}")


def test_register_requires_service_secret(admin_client: TestClient) -> None:
    # No bearer.
    r = admin_client.post(REG, json={"display_name": "no-secret-bot"})
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "auth.service_secret_missing"
    # Wrong bearer.
    r = admin_client.post(
        REG, json={"display_name": "no-secret-bot"}, headers={"Authorization": "Bearer nope"}
    )
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "auth.service_secret_invalid"


def test_register_creates_pending_request_and_approval(admin_client: TestClient) -> None:
    reg = _register(
        admin_client,
        "scout",
        rationale="I want to publish status modules",
    )
    assert reg["status"] == "pending"
    assert reg["registration_id"].startswith("areg_")
    assert reg["claim_token"].startswith("hb_reg_")
    assert reg["expires_at"]

    listing = admin_client.get("/api/v1/agent-registrations?status=pending")
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["requested_name"] == "scout"
    assert items[0]["status"] == "pending"
    assert "claim_token" not in items[0]

    apr_id = _pending_approval_id(admin_client, reg["registration_id"])
    detail = admin_client.get(f"/api/v1/approval-requests/{apr_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["action_type"] == "register_agent"
    assert body["registration_preview"]["requested_name"] == "scout"


def test_claim_while_pending_returns_pending(admin_client: TestClient) -> None:
    reg = _register(admin_client, "waiter")
    r = admin_client.post(
        CLAIM, json={"claim_token": reg["claim_token"]}, headers=_secret_headers()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["api_key"] is None


def test_approve_then_claim_mints_key_once(admin_client: TestClient) -> None:
    reg = _register(admin_client, "claude-onboard")
    rid = reg["registration_id"]
    apr_id = _pending_approval_id(admin_client, rid)

    appr = admin_client.post(f"/api/v1/approval-requests/{apr_id}/approve", json={})
    assert appr.status_code == 200, appr.text
    assert appr.json()["applied"] is True

    claim = admin_client.post(
        CLAIM, json={"claim_token": reg["claim_token"]}, headers=_secret_headers()
    )
    assert claim.status_code == 200, claim.text
    body = claim.json()
    assert body["status"] == "approved"
    assert body["api_key"].startswith("hb_agt_")
    assert body["agent_id"].startswith("agt_")
    api_key = body["api_key"]

    resolved = admin_client.post(
        "/api/v1/internal/auth/resolve-key", json={"api_key": api_key}, headers=_secret_headers()
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["agent_id"] == body["agent_id"]

    agents = admin_client.get("/api/v1/agents?limit=200").json()["items"]
    assert any(a["id"] == body["agent_id"] and a["status"] == "active" for a in agents)

    again = admin_client.post(
        CLAIM, json={"claim_token": reg["claim_token"]}, headers=_secret_headers()
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "claimed"
    assert again.json()["api_key"] is None


def test_approve_with_permissions_override(admin_client: TestClient) -> None:
    reg = _register(admin_client, "scoped-bot")
    apr_id = _pending_approval_id(admin_client, reg["registration_id"])
    admin_client.post(
        f"/api/v1/approval-requests/{apr_id}/approve",
        json={"registration": {"permissions": {"can_write": True}}},
    )
    claim = admin_client.post(
        CLAIM, json={"claim_token": reg["claim_token"]}, headers=_secret_headers()
    ).json()
    aid = claim["agent_id"]
    agent = admin_client.get(f"/api/v1/agents/{aid}").json()
    assert agent["permissions"] == {"can_write": True}


def test_deny_then_claim_returns_denied(admin_client: TestClient) -> None:
    reg = _register(admin_client, "rejected-bot")
    apr_id = _pending_approval_id(admin_client, reg["registration_id"])
    deny = admin_client.post(
        f"/api/v1/approval-requests/{apr_id}/deny",
        json={"reason": "not today"},
    )
    assert deny.status_code == 200, deny.text

    listing = admin_client.get(f"/api/v1/agent-registrations?status=denied")
    assert any(x["id"] == reg["registration_id"] for x in listing.json()["items"])

    claim = admin_client.post(
        CLAIM, json={"claim_token": reg["claim_token"]}, headers=_secret_headers()
    ).json()
    assert claim["status"] == "denied"
    assert claim["reason"] == "not today"
    assert claim["api_key"] is None


def test_register_name_collision_with_existing_agent(admin_client: TestClient) -> None:
    created = admin_client.post("/api/v1/agents", json={"display_name": "dup-name"})
    assert created.status_code == 201, created.text
    r = admin_client.post(REG, json={"display_name": "dup-name"}, headers=_secret_headers())
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "agent.name_taken"


def test_claim_unknown_token_is_not_found(admin_client: TestClient) -> None:
    r = admin_client.post(
        CLAIM, json={"claim_token": "hb_reg_does_not_exist"}, headers=_secret_headers()
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "registration.not_found"


def test_approve_already_decided_conflicts(admin_client: TestClient) -> None:
    reg = _register(admin_client, "twice")
    apr_id = _pending_approval_id(admin_client, reg["registration_id"])
    assert admin_client.post(f"/api/v1/approval-requests/{apr_id}/approve", json={}).status_code == 200
    again = admin_client.post(f"/api/v1/approval-requests/{apr_id}/approve", json={})
    assert again.status_code == 400, again.text
    assert again.json()["code"] == "approval_request.not_pending"


def test_queue_cap_refuses_excess_pending(
    admin_client: TestClient, monkeypatch
) -> None:
    from app import config as cfg

    monkeypatch.setenv("PDASH_AGENT_REGISTRATION_MAX_PENDING", "1")
    cfg.reset_settings_cache()
    try:
        first = admin_client.post(REG, json={"display_name": "cap-a"}, headers=_secret_headers())
        assert first.status_code == 201, first.text
        second = admin_client.post(REG, json={"display_name": "cap-b"}, headers=_secret_headers())
        assert second.status_code == 429, second.text
        assert second.json()["code"] == "registration.queue_full"
    finally:
        cfg.reset_settings_cache()


def test_register_duplicate_live_name_rejected(admin_client: TestClient) -> None:
    first = admin_client.post(REG, json={"display_name": "dup-reg"}, headers=_secret_headers())
    assert first.status_code == 201, first.text
    second = admin_client.post(REG, json={"display_name": "dup-reg"}, headers=_secret_headers())
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "registration.name_pending"


def test_expired_pending_claim_returns_expired(admin_client: TestClient, monkeypatch) -> None:
    from app import config as cfg

    monkeypatch.setenv("PDASH_AGENT_REGISTRATION_TTL_SECONDS", "-10")
    cfg.reset_settings_cache()
    try:
        reg = _register(admin_client, "stale-claim")
        claim = admin_client.post(
            CLAIM, json={"claim_token": reg["claim_token"]}, headers=_secret_headers()
        ).json()
        assert claim["status"] == "expired"
        assert claim["api_key"] is None
    finally:
        cfg.reset_settings_cache()


def test_expired_pending_cannot_be_approved(admin_client: TestClient, monkeypatch) -> None:
    from app import config as cfg

    monkeypatch.setenv("PDASH_AGENT_REGISTRATION_TTL_SECONDS", "-10")
    cfg.reset_settings_cache()
    try:
        reg = _register(admin_client, "stale-approve")
        apr_id = _pending_approval_id(admin_client, reg["registration_id"])
        appr = admin_client.post(f"/api/v1/approval-requests/{apr_id}/approve", json={})
        assert appr.status_code == 200, appr.text
        assert appr.json()["applied"] is False
    finally:
        cfg.reset_settings_cache()
