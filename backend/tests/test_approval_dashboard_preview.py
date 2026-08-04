"""Tests for dashboard preview on approval request detail."""

from __future__ import annotations

from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    internal_headers,
    register_agent,
)


def _create_custom_page(admin_client: TestClient, *, slug: str, name: str = "Preview") -> str:
    resp = admin_client.post(
        "/api/v1/pages",
        json={"slug": slug, "name": name, "type": "custom"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_user_module(
    admin_client: TestClient, page_id: str, *, title: str, body: str, position: int = 0
) -> str:
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "title": title,
            "position": position,
            "data": {"body": body},
            "config": {},
            "owner_kind": "user",
            "owner_id": "admin",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _detail(admin_client: TestClient, request_id: str) -> dict:
    resp = admin_client.get(f"/api/v1/approval-requests/{request_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_dashboard_preview_create_module(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="preview-create")
    secret = get_service_secret()
    page_id = _create_custom_page(admin_client, slug="preview-create")
    sibling_id = _create_user_module(
        admin_client, page_id, title="Existing", body="stay", position=0
    )

    r = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "title": "New tile",
            "position": 1,
            "data": {"body": "hello preview"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="preview-create-1"),
    )
    assert r.status_code == 202, r.text
    req_id = r.json()["request_id"]
    provisional_id = r.json().get("provisional_id") or r.json().get("module_id")

    detail = _detail(admin_client, req_id)
    preview = detail["dashboard_preview"]
    assert preview is not None
    assert preview["page"]["id"] == page_id
    assert preview["highlight"]["change"] == "create"
    assert len(preview["modules"]) == 2
    ids = {m["id"] for m in preview["modules"]}
    assert sibling_id in ids
    created = next(m for m in preview["modules"] if m["title"] == "New tile")
    assert created["data"]["body"] == "hello preview"
    assert preview["highlight"]["module_ids"] == [created["id"]]
    if provisional_id:
        assert created["id"] == provisional_id


def test_dashboard_preview_update_module(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="preview-update")
    secret = get_service_secret()
    page_id = _create_custom_page(admin_client, slug="preview-update")
    _create_user_module(admin_client, page_id, title="Sibling", body="unchanged", position=0)
    mod_id = _create_user_module(
        admin_client, page_id, title="Target", body="old", position=1
    )

    upd = admin_client.post(
        "/api/v1/internal/update-module",
        json={"id": mod_id, "patch": {"data": {"body": "new preview text"}}},
        headers=internal_headers(agent_id, secret, idempotency_key="preview-update-1"),
    )
    assert upd.status_code == 202, upd.text
    req_id = upd.json()["request_id"]

    preview = _detail(admin_client, req_id)["dashboard_preview"]
    assert preview is not None
    assert preview["highlight"]["change"] == "update"
    assert preview["highlight"]["module_ids"] == [mod_id]
    target = next(m for m in preview["modules"] if m["id"] == mod_id)
    assert target["data"]["body"] == "new preview text"
    sibling = next(m for m in preview["modules"] if m["title"] == "Sibling")
    assert sibling["data"]["body"] == "unchanged"


def test_dashboard_preview_delete_module(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="preview-delete")
    secret = get_service_secret()
    page_id = _create_custom_page(admin_client, slug="preview-delete")
    _create_user_module(admin_client, page_id, title="Keep", body="stay", position=0)
    mod_id = _create_user_module(
        admin_client, page_id, title="Remove me", body="gone", position=1
    )

    dele = admin_client.post(
        "/api/v1/internal/delete-module",
        json={"id": mod_id},
        headers=internal_headers(agent_id, secret, idempotency_key="preview-delete-1"),
    )
    assert dele.status_code == 202, dele.text
    req_id = dele.json()["request_id"]

    preview = _detail(admin_client, req_id)["dashboard_preview"]
    assert preview is not None
    assert preview["highlight"]["change"] == "delete"
    assert preview["highlight"]["removed_module_ids"] == [mod_id]
    assert mod_id not in {m["id"] for m in preview["modules"]}
    assert len(preview["modules"]) == 1
    removed = preview["highlight"]["removed_modules"]
    assert len(removed) == 1
    assert removed[0]["id"] == mod_id
    assert removed[0]["title"] == "Remove me"


def test_dashboard_preview_create_page(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="preview-page")
    secret = get_service_secret()

    r = admin_client.post(
        "/api/v1/internal/propose-page",
        json={"name": "Ops", "slug": "ops-preview-test", "description": "Ops board"},
        headers=internal_headers(agent_id, secret, idempotency_key="preview-page-1"),
    )
    assert r.status_code == 202, r.text
    req_id = r.json()["request_id"]

    preview = _detail(admin_client, req_id)["dashboard_preview"]
    assert preview is not None
    assert preview["page"]["name"] == "Ops"
    assert preview["page"]["slug"] == "ops-preview-test"
    assert preview["page"]["description"] == "Ops board"
    assert preview["modules"] == []
    assert preview["highlight"]["change"] == "create_page"
