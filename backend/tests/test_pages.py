"""Page CRUD tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_get_patch_delete_page(admin_client: TestClient) -> None:
    resp = admin_client.post(
        "/api/v1/pages",
        json={"slug": "ops", "name": "Operations", "type": "custom"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    page_id = body["id"]
    assert page_id.startswith("pg_")

    resp = admin_client.get(f"/api/v1/pages/{page_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Operations"

    resp = admin_client.get("/api/v1/pages/by-slug/ops")
    assert resp.status_code == 200
    assert resp.json()["id"] == page_id

    resp = admin_client.patch(
        f"/api/v1/pages/{page_id}", json={"name": "Ops Page"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Ops Page"

    resp = admin_client.delete(f"/api/v1/pages/{page_id}")
    assert resp.status_code == 204

    resp = admin_client.get(f"/api/v1/pages/{page_id}")
    assert resp.status_code == 404

    resp = admin_client.get("/api/v1/pages/by-slug/ops")
    assert resp.status_code == 404


def test_duplicate_slug_conflicts(admin_client: TestClient) -> None:
    admin_client.post("/api/v1/pages", json={"slug": "dash", "name": "Dash", "type": "custom"})
    resp = admin_client.post("/api/v1/pages", json={"slug": "dash", "name": "Dash2", "type": "custom"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "page.slug_taken"


def test_home_page_undeletable(admin_client: TestClient) -> None:
    pages = admin_client.get("/api/v1/pages").json()["items"]
    home = next(p for p in pages if p["slug"] == "home")
    resp = admin_client.delete(f"/api/v1/pages/{home['id']}")
    assert resp.status_code == 400
    assert resp.json()["code"] == "page.cannot_delete_home"


def test_invalid_slug_rejected(admin_client: TestClient) -> None:
    resp = admin_client.post(
        "/api/v1/pages", json={"slug": "Bad Slug!", "name": "x", "type": "custom"}
    )
    # pydantic regex rejection → 422
    assert resp.status_code == 422
