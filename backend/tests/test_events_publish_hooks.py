"""Verify every CRUD path emits the expected event(s) on the bus.

We snapshot events via the bus's internal ring buffers (which capture every
publish regardless of subscribers) so the assertions are race-free.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)


def _collect_topic(topic: str) -> list:
    from app.events import bus
    ring = bus._ring.get(topic, [])
    return [ev for _ts, ev in ring]


def _reset_bus() -> None:
    from app.events import bus
    bus.reset()


# ---------------------------------------------------------------------------
# Admin module CRUD publishes page:* and module:* events.
# ---------------------------------------------------------------------------


def test_admin_create_module_publishes(admin_client: TestClient) -> None:
    _reset_bus()
    resp = admin_client.post(
        "/api/v1/pages", json={"slug": "test-page", "name": "Test"}
    )
    assert resp.status_code == 201
    page_id = resp.json()["id"]
    assert any(e.kind == "page_added" for e in _collect_topic("pages"))

    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "owner_kind": "user",
            "owner_id": "admin",
            "data": {"body": "hello"},
            "config": {},
            "permissions": {},
            "position": 0,
        },
    )
    assert resp.status_code == 201
    mod_id = resp.json()["id"]
    page_events = _collect_topic(f"page:{page_id}")
    mod_events = _collect_topic(f"module:{mod_id}")
    assert any(e.kind == "module_added" for e in page_events)
    assert any(e.kind == "module_added" for e in mod_events)


def test_admin_patch_module_publishes(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/pages", json={"slug": "p2", "name": "P2"})
    page_id = resp.json()["id"]
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "owner_kind": "user",
            "owner_id": "admin",
            "data": {"body": "x"},
            "config": {},
            "permissions": {},
        },
    )
    mod_id = resp.json()["id"]
    _reset_bus()
    resp = admin_client.patch(
        f"/api/v1/modules/{mod_id}", json={"data": {"body": "updated"}}
    )
    assert resp.status_code == 200
    assert any(e.kind == "module_updated" for e in _collect_topic(f"page:{page_id}"))
    assert any(e.kind == "module_updated" for e in _collect_topic(f"module:{mod_id}"))


def test_admin_delete_module_publishes(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/pages", json={"slug": "p3", "name": "P3"})
    page_id = resp.json()["id"]
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "owner_kind": "user",
            "owner_id": "admin",
            "data": {"body": "x"},
            "config": {},
            "permissions": {},
        },
    )
    mod_id = resp.json()["id"]
    _reset_bus()
    resp = admin_client.delete(f"/api/v1/modules/{mod_id}")
    assert resp.status_code == 204
    assert any(e.kind == "module_removed" for e in _collect_topic(f"page:{page_id}"))


def test_admin_reorder_publishes_modules_reordered(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/pages", json={"slug": "p4", "name": "P4"})
    page_id = resp.json()["id"]
    ids: list[str] = []
    for i in range(3):
        resp = admin_client.post(
            "/api/v1/modules",
            json={
                "type": "markdown",
                "page_id": page_id,
                "owner_kind": "user",
                "owner_id": "admin",
                "data": {"body": f"m{i}"},
                "config": {},
                "permissions": {},
                "position": i,
            },
        )
        ids.append(resp.json()["id"])
    _reset_bus()
    resp = admin_client.post(
        "/api/v1/modules/reorder",
        json={"page_id": page_id, "ids": list(reversed(ids))},
    )
    assert resp.status_code == 200
    events = _collect_topic(f"page:{page_id}")
    reordered = [e for e in events if e.kind == "modules_reordered"]
    assert len(reordered) == 1
    assert reordered[0].payload["order"] == list(reversed(ids))


# ---------------------------------------------------------------------------
# Page CRUD publishes "pages" channel.
# ---------------------------------------------------------------------------


def test_admin_page_lifecycle_publishes(admin_client: TestClient) -> None:
    _reset_bus()
    resp = admin_client.post("/api/v1/pages", json={"slug": "lc", "name": "Lifecycle"})
    assert resp.status_code == 201
    pid = resp.json()["id"]
    resp = admin_client.patch(f"/api/v1/pages/{pid}", json={"name": "Renamed"})
    assert resp.status_code == 200
    resp = admin_client.delete(f"/api/v1/pages/{pid}")
    assert resp.status_code == 204
    kinds = [e.kind for e in _collect_topic("pages")]
    assert "page_added" in kinds
    assert "page_updated" in kinds
    assert "page_removed" in kinds


# ---------------------------------------------------------------------------
# Audit -> activity channel
# ---------------------------------------------------------------------------


def test_audit_write_event_publishes_activity(admin_client: TestClient) -> None:
    _reset_bus()
    resp = admin_client.post("/api/v1/pages", json={"slug": "act", "name": "Act"})
    assert resp.status_code == 201
    events = _collect_topic("activity")
    assert any(
        e.kind == "activity_appended" and e.payload["action_type"] == "create_page"
        for e in events
    )


# ---------------------------------------------------------------------------
# Approval orchestrator publishes approvals events.
# ---------------------------------------------------------------------------


def test_internal_propose_module_pending_publishes_approval_pending(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="snoop-pending")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _reset_bus()
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        headers=internal_headers(agent_id, secret, idempotency_key="kp1"),
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "from agent"},
            "config": {},
        },
    )
    assert resp.status_code == 202, resp.text
    events = _collect_topic("approvals")
    pending = [e for e in events if e.kind == "approval_pending"]
    assert pending, [e.kind for e in events]
    assert pending[0].payload["action_type"] == "create_module"


def test_internal_update_module_auto_approves_publishes_decided_and_updated(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="snoop-update")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # First propose a module and approve it admin-side.
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        headers=internal_headers(agent_id, secret, idempotency_key="upd1"),
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "p1"},
            "config": {},
        },
    )
    assert resp.status_code == 202
    request_id = resp.json()["request_id"]
    resp = admin_client.post(
        f"/api/v1/approval-requests/{request_id}/approve",
        json={"reason": "ok"},
    )
    assert resp.status_code == 200
    mod_id = resp.json()["apply_result"]["module_id"]

    _reset_bus()
    # Owner update_module_data is auto-approved by the built-in rule.
    resp = admin_client.post(
        "/api/v1/internal/update-module",
        headers=internal_headers(agent_id, secret, idempotency_key="upd2"),
        json={"id": mod_id, "patch": {"data": {"body": "p2"}}},
    )
    assert resp.status_code == 200, resp.text
    approvals = [e for e in _collect_topic("approvals") if e.kind == "approval_decided"]
    assert approvals, "expected approval_decided after auto_approve"
    page_events = [
        e for e in _collect_topic(f"page:{page_id}") if e.kind == "module_updated"
    ]
    assert page_events


def test_admin_approve_pending_publishes_approval_decided(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="snoop-approve")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        headers=internal_headers(agent_id, secret, idempotency_key="ap1"),
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "x"},
            "config": {},
        },
    )
    request_id = resp.json()["request_id"]
    _reset_bus()
    resp = admin_client.post(
        f"/api/v1/approval-requests/{request_id}/approve",
        json={"reason": "ok"},
    )
    assert resp.status_code == 200
    approvals = [e for e in _collect_topic("approvals") if e.kind == "approval_decided"]
    assert approvals
    assert approvals[0].payload["outcome"] == "applied"


def test_admin_deny_pending_publishes_decided_denied(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="snoop-deny")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        headers=internal_headers(agent_id, secret, idempotency_key="dn1"),
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "x"},
            "config": {},
        },
    )
    request_id = resp.json()["request_id"]
    _reset_bus()
    resp = admin_client.post(
        f"/api/v1/approval-requests/{request_id}/deny",
        json={"reason": "too noisy, batch these"},
    )
    assert resp.status_code == 200
    approvals = [e for e in _collect_topic("approvals") if e.kind == "approval_decided"]
    assert approvals
    assert approvals[0].payload["outcome"] == "denied"
    # The admin's note rides the event so the MCP decision_cache can surface it
    # to the agent live (decision_cache._apply_event merges payload fields).
    assert approvals[0].payload["decision_reason"] == "too noisy, batch these"


def test_log_stream_append_publishes_log_appended(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="snoop-log")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # Create a log_stream module (admin path, bypasses approval), owned by agent.
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "log_stream",
            "page_id": page_id,
            "owner_kind": "agent",
            "owner_id": agent_id,
            "data": {"entries": []},
            "config": {"ring_buffer_size": 50},
            "permissions": {},
        },
    )
    assert resp.status_code == 201
    mod_id = resp.json()["id"]
    _reset_bus()
    resp = admin_client.post(
        "/api/v1/internal/append-log",
        headers=internal_headers(agent_id, secret, idempotency_key="lg1"),
        json={"module_id": mod_id, "lines": [{"message": "hi"}]},
    )
    assert resp.status_code == 200, resp.text
    log_events = _collect_topic(f"log_stream:{mod_id}")
    assert log_events
    assert log_events[0].kind == "log_appended"
    assert log_events[0].payload["entries"][0]["message"] == "hi"


def test_internal_propose_page_pending_publishes(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="snoop-page")
    secret = get_service_secret()
    _reset_bus()
    resp = admin_client.post(
        "/api/v1/internal/propose-page",
        headers=internal_headers(agent_id, secret, idempotency_key="pp1"),
        json={"name": "Agent Page", "slug": "agent-page"},
    )
    assert resp.status_code == 202, resp.text
    approvals = [e for e in _collect_topic("approvals") if e.kind == "approval_pending"]
    assert approvals
    assert approvals[0].payload["action_type"] == "create_page"
