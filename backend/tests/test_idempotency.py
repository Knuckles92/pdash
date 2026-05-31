"""Idempotency-Key replay tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _home_page_id(client: TestClient) -> str:
    resp = client.get("/api/v1/pages")
    items = resp.json()["items"]
    return next(item["id"] for item in items if item["slug"] == "home")


def test_repeat_post_with_same_key_returns_cached_response(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    body = {
        "type": "markdown",
        "page_id": page_id,
        "data": {"body": "hi"},
        "config": {},
    }

    resp1 = admin_client.post(
        "/api/v1/modules",
        json=body,
        headers={"Idempotency-Key": "abc-123"},
    )
    assert resp1.status_code == 201, resp1.text
    first_id = resp1.json()["id"]

    # Same key — should return the cached payload, with a replay marker.
    resp2 = admin_client.post(
        "/api/v1/modules",
        json=body,
        headers={"Idempotency-Key": "abc-123"},
    )
    assert resp2.status_code == 201
    assert resp2.json()["id"] == first_id
    assert resp2.headers.get("X-Idempotency-Replay") == "true"


def test_different_keys_create_independent_rows(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    body = {
        "type": "markdown",
        "page_id": page_id,
        "data": {"body": "hello"},
        "config": {},
    }
    r1 = admin_client.post("/api/v1/modules", json=body, headers={"Idempotency-Key": "k1"})
    r2 = admin_client.post("/api/v1/modules", json=body, headers={"Idempotency-Key": "k2"})
    assert r1.json()["id"] != r2.json()["id"]


def test_no_key_creates_separate_each_time(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    body = {
        "type": "markdown",
        "page_id": page_id,
        "data": {"body": "no-idem"},
        "config": {},
    }
    r1 = admin_client.post("/api/v1/modules", json=body)
    r2 = admin_client.post("/api/v1/modules", json=body)
    assert r1.json()["id"] != r2.json()["id"]
