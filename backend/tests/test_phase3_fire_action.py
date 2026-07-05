"""Tests for ``POST /api/v1/internal/fire-action``.

Phase 3 supports webhook + local_script kinds. Webhook execution is exercised
via a local stub server (httpx mock-respond) by hitting a real loopback port
would require fixtures; we use a 127.0.0.1 endpoint that's guaranteed to
refuse so we can verify the result.ok=False path. For the local_script kind we
spawn /usr/bin/env true to verify the success path.
"""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)


@pytest.mark.skipif(shutil.which("true") is None, reason="`true` shell builtin not available")
def test_fire_action_local_script_success(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="fire-script")
    secret = get_service_secret()
    # Create an action_target of kind=local_script
    target = admin_client.post(
        "/api/v1/action-targets",
        json={
            "name": "noop-true",
            "kind": "local_script",
            "config": {"command": "/usr/bin/env true", "timeout_seconds": 5},
            "mode": "sync",
        },
    )
    assert target.status_code == 201, target.text
    tid = target.json()["id"]

    # The default rule for fire_action_button is prompt — so this comes back pending.
    resp = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid, "payload": {"hello": "world"}},
        headers=internal_headers(agent_id, secret, idempotency_key="fa-1"),
    )
    assert resp.status_code == 202

    # Approve and assert execution_result.ok is True
    req_id = resp.json()["request_id"]
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={}
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["applied"] is True

    # The detail endpoint includes execution_result
    detail = admin_client.get(f"/api/v1/approval-requests/{req_id}")
    body = detail.json()
    assert body["status"] == "applied"
    assert body["executed_at"] is not None
    result = body["execution_result"]
    assert result is not None
    assert result["ok"] is True
    assert result["exit_code"] == 0


def test_fire_action_webhook_against_unroutable_url(admin_client: TestClient) -> None:
    """Webhook that fails connection → execution_result.ok=False, status stays applied."""
    agent_id, _ = register_agent(admin_client, name="fire-webhook")
    secret = get_service_secret()
    target = admin_client.post(
        "/api/v1/action-targets",
        json={
            "name": "unreachable",
            "kind": "webhook",
            "config": {
                "url": "http://127.0.0.1:1/will-not-connect",
                "timeout_seconds": 1,
            },
            "mode": "sync",
        },
    )
    tid = target.json()["id"]
    resp = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid},
        headers=internal_headers(agent_id, secret, idempotency_key="fa-web-1"),
    )
    assert resp.status_code == 202
    req_id = resp.json()["request_id"]
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={}
    )
    assert approve.status_code == 200

    detail = admin_client.get(f"/api/v1/approval-requests/{req_id}").json()
    assert detail["status"] == "applied"
    assert detail["executed_at"] is not None
    assert detail["execution_result"]["ok"] is False


def test_fire_action_unknown_target_404(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="fire-unknown")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": "act_nonexistent"},
        headers=internal_headers(agent_id, secret, idempotency_key="fa-404"),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "action_target.not_found"
