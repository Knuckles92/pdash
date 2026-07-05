"""Coverage for the smaller internal endpoints: whoami, my-modules,
my-pending-requests, module-schema, propose-page."""

from __future__ import annotations

from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)


def test_whoami(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="who")
    secret = get_service_secret()
    resp = admin_client.get(
        "/api/v1/internal/whoami",
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent"]["id"] == agent_id
    assert body["agent"]["display_name"] == "who"


def test_module_schema(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="schema")
    secret = get_service_secret()
    resp = admin_client.get(
        "/api/v1/internal/module-schema/markdown",
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200
    assert resp.json()["type"] == "markdown"


def test_my_modules_only_returns_owned(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="mine")
    other_id, _ = register_agent(admin_client, name="other")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # Create one module owned by agent, one by 'other'
    admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "mine"},
            "config": {},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "theirs"},
            "config": {},
            "owner_kind": "agent",
            "owner_id": other_id,
        },
    )

    resp = admin_client.get(
        "/api/v1/internal/my-modules",
        headers=internal_headers(agent_id, secret),
    )
    items = resp.json()["items"]
    assert all(i["owner_id"] == agent_id for i in items)
    assert len(items) == 1


def test_my_pending_requests(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pending-self")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "x"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="ms-1"),
    )
    resp = admin_client.get(
        "/api/v1/internal/my-pending-requests",
        headers=internal_headers(agent_id, secret),
    )
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "pending"
    # Still pending → no decision yet, so the reason is null.
    assert items[0]["decision_reason"] is None


def test_my_pending_requests_surfaces_decision_reason(admin_client: TestClient) -> None:
    """When the admin denies with a note, the agent sees it on poll so it can
    follow the guidance instead of re-proposing the same denied write."""
    agent_id, _ = register_agent(admin_client, name="reason-self")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    propose = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "x"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="reason-1"),
    )
    assert propose.status_code == 202, propose.text
    request_id = propose.json()["request_id"]

    deny = admin_client.post(
        f"/api/v1/approval-requests/{request_id}/deny",
        json={"reason": "put this on the ops page, not home"},
    )
    assert deny.status_code == 200, deny.text

    resp = admin_client.get(
        "/api/v1/internal/my-pending-requests",
        params={"status_filter": "denied"},
        headers=internal_headers(agent_id, secret),
    )
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "denied"
    assert items[0]["decision_reason"] == "put this on the ops page, not home"


def test_propose_page_returns_pending(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pager")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/propose-page",
        json={"name": "Agent Workspace", "slug": "agent-ws"},
        headers=internal_headers(agent_id, secret, idempotency_key="pp-1"),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"

    # Approve + page appears
    approve = admin_client.post(
        f"/api/v1/approval-requests/{body['request_id']}/approve", json={}
    )
    assert approve.status_code == 200
    assert approve.json()["applied"] is True

    # Listing pages shows it now
    pages = admin_client.get("/api/v1/pages").json()["items"]
    assert any(p["slug"] == "agent-ws" for p in pages)


def test_propose_page_existing_slug_conflicts(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pager2")
    secret = get_service_secret()
    # home already exists with slug 'home'
    resp = admin_client.post(
        "/api/v1/internal/propose-page",
        json={"name": "Home Clone", "slug": "home"},
        headers=internal_headers(agent_id, secret, idempotency_key="pp-2"),
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "page.slug_taken"
