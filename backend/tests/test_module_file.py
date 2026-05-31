"""Tests for the new ``file`` module type (schema + create paths)."""

from __future__ import annotations

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)
from fastapi.testclient import TestClient


def test_file_schema_served(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/module-schemas/file")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "file"
    props = body["data"]["properties"]
    assert "file_id" in props and "kind" in props and "display_name" in props


def test_admin_create_file_module(admin_client: TestClient) -> None:
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "file",
            "page_id": page_id,
            "data": {
                "file_id": "fil_abc",
                "kind": "image",
                "display_name": "Chart",
            },
            "config": {"max_height_px": 300},
            "owner_kind": "user",
            "owner_id": "admin",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["type"] == "file"
    assert resp.json()["data"]["file_id"] == "fil_abc"


def test_file_module_rejects_bad_kind(admin_client: TestClient) -> None:
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "file",
            "page_id": page_id,
            "data": {"file_id": "fil_abc", "kind": "bogus", "display_name": "X"},
            "config": {},
            "owner_kind": "user",
            "owner_id": "admin",
        },
    )
    assert resp.status_code == 400


def test_agent_propose_file_module_pending(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="file-proposer")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "file",
            "page_id": page_id,
            "data": {"file_id": "fil_x", "kind": "document", "display_name": "Doc"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="pf-1"),
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "pending"
