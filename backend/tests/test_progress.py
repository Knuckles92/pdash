"""progress module CRUD + validation tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _home_page_id(client: TestClient) -> str:
    resp = client.get("/api/v1/pages")
    assert resp.status_code == 200
    items = resp.json()["items"]
    return next(item["id"] for item in items if item["slug"] == "home")


def _progress_payload(page_id: str) -> dict:
    return {
        "type": "progress",
        "page_id": page_id,
        "title": "Goals",
        "data": {
            "bars": [
                {
                    "id": "disk",
                    "label": "Disk usage",
                    "current": 1.8,
                    "target": 2,
                    "unit": "TB",
                    "severity": "warning",
                    "hint": "Primary volume",
                },
                {"label": "Backups", "current": 14, "target": 14, "severity": "success"},
            ],
            "updated_at": "2026-06-17T12:00:00.000Z",
        },
        "config": {
            "show_values": True,
            "show_percent": True,
            "density": "normal",
            "sort": "percent-desc",
        },
    }


def test_create_get_patch_delete_progress_module(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    payload = _progress_payload(page_id)

    resp = admin_client.post("/api/v1/modules", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    mod_id = body["id"]
    assert mod_id.startswith("mod_")
    assert body["version"] == 1
    etag = resp.headers["etag"]
    assert etag.startswith("W/")

    # Get
    resp = admin_client.get(f"/api/v1/modules/{mod_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["bars"][0]["label"] == "Disk usage"
    assert resp.headers["etag"] == etag

    # Patch data (drop a bar)
    resp = admin_client.patch(
        f"/api/v1/modules/{mod_id}",
        json={"data": {"bars": [{"label": "Only", "current": 1, "target": 4}]}},
        headers={"If-Match": etag},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["bars"][0]["label"] == "Only"
    assert resp.json()["version"] == 2

    # Patch config (sort + appearance)
    resp = admin_client.patch(
        f"/api/v1/modules/{mod_id}",
        json={"config": {"sort": "label", "appearance": {"theme": "tinted", "color": "emerald"}}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["sort"] == "label"
    assert resp.json()["config"]["appearance"]["color"] == "emerald"

    # Delete
    resp = admin_client.delete(f"/api/v1/modules/{mod_id}")
    assert resp.status_code == 204
    resp = admin_client.get(f"/api/v1/modules/{mod_id}")
    assert resp.status_code == 404


def test_progress_rejects_non_positive_target(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "progress",
            "page_id": page_id,
            "data": {"bars": [{"label": "Bad", "current": 1, "target": 0}]},
            "config": {},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.invalid_payload"


def test_progress_rejects_negative_current(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "progress",
            "page_id": page_id,
            "data": {"bars": [{"label": "Bad", "current": -1, "target": 10}]},
            "config": {},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.invalid_payload"


def test_progress_rejects_unknown_sort_value(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "progress",
            "page_id": page_id,
            "data": {"bars": []},
            "config": {"sort": "by-magic"},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.invalid_payload"


def test_progress_rejects_extra_field(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "progress",
            "page_id": page_id,
            "data": {"bars": [{"label": "X", "current": 1, "target": 2, "bogus": True}]},
            "config": {},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.invalid_payload"
