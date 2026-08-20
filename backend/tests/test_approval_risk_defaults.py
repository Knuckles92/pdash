"""End-to-end: owner create auto-applies, capability still prompts, permissions."""

from __future__ import annotations

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)
from fastapi.testclient import TestClient


def _owned_page(admin_client: TestClient, agent_id: str, slug: str) -> str:
    resp = admin_client.post(
        "/api/v1/pages",
        json={
            "slug": slug,
            "name": slug,
            "type": "agent",
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_owner_create_markdown_on_owned_page_applies(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-own-md")
    secret = get_service_secret()
    page_id = _owned_page(admin_client, agent_id, "risk-own-md")
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "hello"},
            "grid": {"colspan": 2},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="risk-md-1"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "applied"
    assert resp.json()["module"]["grid"]["colspan"] == 2


def test_create_on_home_still_pending(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-home")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={"type": "markdown", "page_id": page_id, "data": {"body": "x"}},
        headers=internal_headers(agent_id, secret, idempotency_key="risk-home-1"),
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"


def test_html_create_on_owned_page_still_pending(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-html")
    secret = get_service_secret()
    page_id = _owned_page(admin_client, agent_id, "risk-html")
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "html",
            "page_id": page_id,
            "data": {"html": "<!doctype html><html><body>x</body></html>"},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="risk-html-1"),
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"


def test_owner_config_auto_applies(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-cfg")
    secret = get_service_secret()
    page_id = _owned_page(admin_client, agent_id, "risk-cfg")
    created = admin_client.post(
        "/api/v1/internal/propose-module",
        json={"type": "markdown", "page_id": page_id, "data": {"body": "x"}},
        headers=internal_headers(agent_id, secret, idempotency_key="risk-cfg-1"),
    )
    assert created.status_code == 200, created.text
    mod_id = created.json()["module"]["id"]
    resp = admin_client.post(
        "/api/v1/internal/update-module",
        json={
            "id": mod_id,
            "patch": {"config": {"appearance": {"color": "emerald"}}},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="risk-cfg-2"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "applied"


def test_table_column_change_prompts(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-cols")
    secret = get_service_secret()
    page_id = _owned_page(admin_client, agent_id, "risk-cols")
    created = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "table",
            "page_id": page_id,
            "data": {
                "columns": [{"id": "n", "label": "N", "type": "text"}],
                "rows": [{"cells": {"n": "a"}}],
            },
        },
        headers=internal_headers(agent_id, secret, idempotency_key="risk-cols-1"),
    )
    assert created.status_code == 200, created.text
    mod_id = created.json()["module"]["id"]
    resp = admin_client.post(
        "/api/v1/internal/update-module",
        json={
            "id": mod_id,
            "patch": {
                "data": {
                    "columns": [{"id": "n", "label": "N", "type": "number"}],
                    "rows": [{"cells": {"n": 1}}],
                }
            },
        },
        headers=internal_headers(agent_id, secret, idempotency_key="risk-cols-2"),
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "pending"


def test_iframe_src_not_allowlisted_rejected(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-ifr")
    secret = get_service_secret()
    page_id = _owned_page(admin_client, agent_id, "risk-ifr")
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "iframe",
            "page_id": page_id,
            "data": {"src": "https://evil.example/"},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="risk-ifr-1"),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "iframe_host_not_allowed"


def test_permissions_restrict_module_type(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-perm")
    admin_client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"permissions": {"allowed_module_types": ["markdown"]}},
    )
    secret = get_service_secret()
    page_id = _owned_page(admin_client, agent_id, "risk-perm")
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "key_value",
            "page_id": page_id,
            "data": {"fields": [{"key": "a", "value": "1"}]},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="risk-perm-1"),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "agent.permission_denied"


def test_merge_partial_data_on_update(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-merge")
    secret = get_service_secret()
    page_id = _owned_page(admin_client, agent_id, "risk-merge")
    created = admin_client.post(
        "/api/v1/internal/propose-module",
        json={"type": "markdown", "page_id": page_id, "data": {"body": "one"}},
        headers=internal_headers(agent_id, secret, idempotency_key="risk-merge-1"),
    )
    mod_id = created.json()["module"]["id"]
    resp = admin_client.post(
        "/api/v1/internal/update-module",
        json={"id": mod_id, "patch": {"data": {"body": "two"}}},
        headers=internal_headers(agent_id, secret, idempotency_key="risk-merge-2"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["module"]["data"]["body"] == "two"


def test_fire_owned_button_auto_applies(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="risk-fire")
    secret = get_service_secret()
    page_id = _owned_page(admin_client, agent_id, "risk-fire")
    target = admin_client.post(
        "/api/v1/action-targets",
        json={
            "name": "risk-noop",
            "kind": "webhook",
            "config": {
                "url": "http://127.0.0.1:1/nope",
                "timeout_seconds": 1,
            },
            "mode": "sync",
        },
    )
    assert target.status_code == 201, target.text
    tid = target.json()["id"]
    # action_button create still prompts
    propose = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "action_button",
            "page_id": page_id,
            "data": {"label": "Go", "action_target_id": tid},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="risk-fire-1"),
    )
    assert propose.status_code == 202, propose.text
    approve = admin_client.post(
        f"/api/v1/approval-requests/{propose.json()['request_id']}/approve", json={}
    )
    assert approve.status_code == 200, approve.text
    module_id = approve.json()["request"]["target_id"]
    fire = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid, "module_id": module_id},
        headers=internal_headers(agent_id, secret, idempotency_key="risk-fire-2"),
    )
    # webhook will fail to connect but the request itself should auto-apply
    assert fire.status_code == 200, fire.text
    assert fire.json()["status"] == "applied"
