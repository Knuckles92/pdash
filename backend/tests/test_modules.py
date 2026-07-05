"""Module CRUD round-trip tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


DEFAULT_EXAMPLE_TYPES = {
    "notification",
    "markdown",
    "key_value",
    "table",
    "timeseries",
    "log_stream",
    "link_list",
    "iframe",
    "action_button",
    "progress",
}


def _home_page_id(client: TestClient) -> str:
    resp = client.get("/api/v1/pages")
    assert resp.status_code == 200
    items = resp.json()["items"]
    return next(item["id"] for item in items if item["slug"] == "home")


def test_fresh_home_page_seeds_default_examples(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.get(f"/api/v1/modules?page_id={page_id}&limit=200")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]

    assert len(items) == len(DEFAULT_EXAMPLE_TYPES)
    assert {item["type"] for item in items} == DEFAULT_EXAMPLE_TYPES
    for item in items:
        assert item["permissions"]["pdash_default_example"] is True
        assert item["permissions"]["seed_version"] == 1


def test_create_get_patch_delete_module(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)

    # Create a markdown module
    payload = {
        "type": "markdown",
        "page_id": page_id,
        "title": "Welcome",
        "data": {"body": "# hello"},
        "config": {"collapsed_by_default": False, "max_height_px": 400},
    }
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
    assert resp.json()["title"] == "Welcome"
    assert resp.headers["etag"] == etag

    # Patch data
    resp = admin_client.patch(
        f"/api/v1/modules/{mod_id}",
        json={"data": {"body": "# updated"}},
        headers={"If-Match": etag},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["body"] == "# updated"
    assert resp.json()["version"] == 2

    # Patch with stale If-Match → 412
    resp = admin_client.patch(
        f"/api/v1/modules/{mod_id}",
        json={"title": "stale"},
        headers={"If-Match": etag},
    )
    assert resp.status_code == 412
    assert resp.json()["code"] == "module.etag_mismatch"

    # Delete
    resp = admin_client.delete(f"/api/v1/modules/{mod_id}")
    assert resp.status_code == 204

    # Now 404
    resp = admin_client.get(f"/api/v1/modules/{mod_id}")
    assert resp.status_code == 404


def test_create_module_invalid_payload(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": 12345},  # not a string
            "config": {},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.invalid_payload"


def test_create_module_unknown_type(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={"type": "not_a_type", "page_id": page_id, "data": {}, "config": {}},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.unknown_type"


def test_module_config_accepts_common_appearance(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "themed"},
            "config": {
                "appearance": {
                    "theme": "tinted",
                    "color": "emerald",
                },
            },
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["config"]["appearance"] == {
        "theme": "tinted",
        "color": "emerald",
    }

    resp = admin_client.patch(
        f"/api/v1/modules/{body['id']}",
        json={
            "config": {
                "appearance": {
                    "theme": "solid",
                    "color": "rose",
                },
            },
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["appearance"] == {
        "theme": "solid",
        "color": "rose",
    }


def test_module_config_rejects_unknown_appearance_color(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "bad color"},
            "config": {
                "appearance": {
                    "theme": "tinted",
                    "color": "ultraviolet",
                },
            },
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.invalid_payload"


def test_reorder_modules(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    ids = []
    for i in range(3):
        resp = admin_client.post(
            "/api/v1/modules",
            json={
                "type": "markdown",
                "page_id": page_id,
                "title": f"m{i}",
                "data": {"body": f"row {i}"},
                "config": {},
            },
        )
        assert resp.status_code == 201
        ids.append(resp.json()["id"])

    # Reverse the order
    reversed_ids = list(reversed(ids))
    resp = admin_client.post(
        "/api/v1/modules/reorder",
        json={"ids": reversed_ids, "page_id": page_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reordered"] == 3

    # Fetch and confirm
    resp = admin_client.get(f"/api/v1/modules?page_id={page_id}&limit=200")
    body = resp.json()
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[reversed_ids[0]]["position"] == 0
    assert by_id[reversed_ids[1]]["position"] == 1
    assert by_id[reversed_ids[2]]["position"] == 2
