"""Tests for ``POST /api/v1/internal/propose-module``.

Covers:

- Built-in rule routes create_module to ``pending`` (default policy).
- Admin approve materializes the real module with the provisional id.
- Idempotency replay returns the cached response with ``X-Idempotency-Replay``.
- ETag concurrency check on update before enqueueing.
- Service-auth: missing service secret => 401, wrong agent => 403.
- ``X-Audit-Id`` header is set on every response.
- Re-running with a narrow rule auto-applies (subsequent calls).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)


def _propose_payload(page_id: str, body: str = "# hello") -> dict:
    return {
        "type": "markdown",
        "page_id": page_id,
        "title": "agent-mod",
        "data": {"body": body},
        "config": {},
    }


def test_missing_service_secret_returns_401(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="missing-secret")
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id),
        headers={"X-Agent-Id": agent_id, "Idempotency-Key": "k1"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.service_secret_missing"


def test_wrong_service_secret_returns_401(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="wrong-secret")
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id),
        headers={
            "Authorization": "Bearer not-the-secret",
            "X-Agent-Id": agent_id,
            "Idempotency-Key": "k1",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.service_secret_invalid"


def test_unknown_agent_id_returns_403(admin_client: TestClient) -> None:
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id),
        headers=internal_headers("agt_unknown", secret, idempotency_key="k1"),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "agent.unknown"


def test_disabled_agent_returns_403(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="disabled-agent")
    admin_client.post(f"/api/v1/agents/{agent_id}/disable")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id),
        headers=internal_headers(agent_id, secret, idempotency_key="k1"),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "agent.disabled"


def test_idempotency_required(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="needs-idem")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id),
        headers=internal_headers(agent_id, secret),  # no idempotency key
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "idempotency.required"


def test_propose_module_routes_to_pending(admin_client: TestClient) -> None:
    """The built-in default rule for create_module is prompt — expect pending."""
    agent_id, _ = register_agent(admin_client, name="propose-pending")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id),
        headers=internal_headers(agent_id, secret, idempotency_key="prop-1"),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["request_id"].startswith("apr_")
    assert body["expires_at"]
    assert resp.headers.get("X-Audit-Id")


def test_idempotency_replay_returns_cached_response(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="replay-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    headers = internal_headers(agent_id, secret, idempotency_key="replay-1")
    payload = _propose_payload(page_id)
    r1 = admin_client.post("/api/v1/internal/propose-module", json=payload, headers=headers)
    assert r1.status_code == 202
    r2 = admin_client.post("/api/v1/internal/propose-module", json=payload, headers=headers)
    assert r2.status_code == 202
    assert r2.json()["request_id"] == r1.json()["request_id"]
    assert r2.headers.get("X-Idempotency-Replay") == "true"


def test_admin_approves_pending_module(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="agent-approve")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    headers = internal_headers(agent_id, secret, idempotency_key="approve-1")
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id, body="# approved"),
        headers=headers,
    )
    assert resp.status_code == 202
    request_id = resp.json()["request_id"]

    # Admin lists pending; one row visible
    lst = admin_client.get("/api/v1/approval-requests?status=pending")
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert any(i["id"] == request_id for i in items)

    # Approve
    approve = admin_client.post(
        f"/api/v1/approval-requests/{request_id}/approve",
        json={"reason": "ok"},
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["applied"] is True
    assert body["request"]["status"] == "applied"

    # The module exists at the provisional id we minted.
    new_mod_id = body["request"]["target_id"]
    assert new_mod_id and new_mod_id.startswith("mod_")
    fetched = admin_client.get(f"/api/v1/modules/{new_mod_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["body"] == "# approved"
    assert fetched.json()["owner_kind"] == "agent"
    assert fetched.json()["owner_id"] == agent_id


def test_approve_with_create_rule_then_next_proposal_auto_applies(
    admin_client: TestClient,
) -> None:
    """After approving + creating a narrow rule, a second propose with the
    matching shape should auto-apply via the new rule."""
    agent_id, _ = register_agent(admin_client, name="auto-apply-after-rule")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # First propose -> pending
    r1 = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id),
        headers=internal_headers(agent_id, secret, idempotency_key="rule-1a"),
    )
    assert r1.status_code == 202
    req_id = r1.json()["request_id"]

    # Approve + create a narrow rule
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve",
        json={
            "reason": "auto-approve future markdown from this agent",
            "create_rule": {
                "agent_id": agent_id,
                "action_type": "create_module",
                "module_type": "markdown",
                "outcome": "auto_approve",
                "priority": 50,
                "apply_to_pending": False,
            },
        },
    )
    assert approve.status_code == 200, approve.text
    assert "rule" in approve.json()

    # Second propose -> should be applied directly
    r2 = admin_client.post(
        "/api/v1/internal/propose-module",
        json=_propose_payload(page_id, body="# second"),
        headers=internal_headers(agent_id, secret, idempotency_key="rule-1b"),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "applied"
    assert r2.json()["module"]["data"]["body"] == "# second"


def test_update_module_etag_stale_returns_412(admin_client: TestClient) -> None:
    """Stale expected_etag short-circuits to 412 before any approval is enqueued."""
    agent_id, _ = register_agent(admin_client, name="etag-stale-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # Create a module via admin (skipping approvals) so the agent can update it.
    mod_resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "starter"},
            "config": {},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    assert mod_resp.status_code == 201
    mod_id = mod_resp.json()["id"]

    # Agent updates with a wrong expected_etag
    resp = admin_client.post(
        "/api/v1/internal/update-module",
        json={
            "id": mod_id,
            "patch": {"data": {"body": "newer"}},
            "expected_etag": 'W/"999"',
        },
        headers=internal_headers(agent_id, secret, idempotency_key="etag-1"),
    )
    assert resp.status_code == 412
    assert resp.json()["code"] == "concurrency.stale"


def test_update_module_owner_self_auto_approves(admin_client: TestClient) -> None:
    """Built-in self-owner update_module_data auto-approves."""
    agent_id, _ = register_agent(admin_client, name="self-owner")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # Create owned by the agent
    mod_resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "v1"},
            "config": {},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    mod_id = mod_resp.json()["id"]

    resp = admin_client.post(
        "/api/v1/internal/update-module",
        json={"id": mod_id, "patch": {"data": {"body": "v2"}}},
        headers=internal_headers(agent_id, secret, idempotency_key="upd-1"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "applied"

    fetched = admin_client.get(f"/api/v1/modules/{mod_id}")
    assert fetched.json()["data"]["body"] == "v2"


def test_propose_module_invalid_type(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="invalid-type-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "not_a_real_type",
            "page_id": page_id,
            "data": {},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="bad-type"),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.unknown_type"


def test_delete_module_pending_then_admin_denies(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="delete-denied")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    # Create a module owned by the agent
    mod_resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "to be deleted"},
            "config": {},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    mod_id = mod_resp.json()["id"]

    resp = admin_client.post(
        "/api/v1/internal/delete-module",
        json={"id": mod_id, "rationale": "stale"},
        headers=internal_headers(agent_id, secret, idempotency_key="del-1"),
    )
    assert resp.status_code == 202, resp.text
    req_id = resp.json()["request_id"]

    deny = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/deny", json={"reason": "still in use"}
    )
    assert deny.status_code == 200
    assert deny.json()["request"]["status"] == "denied"

    # Module should still exist
    fetched = admin_client.get(f"/api/v1/modules/{mod_id}")
    assert fetched.status_code == 200
