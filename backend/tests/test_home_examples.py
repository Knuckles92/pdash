"""Admin API for default Home example modules."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.seed_home import SEED_VERSION

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


def _custom_page_id(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/pages",
        json={"slug": "demo-page", "name": "Demo", "kind": "custom"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _default_example_count(client: TestClient, page_id: str) -> int:
    resp = client.get(f"/api/v1/modules?page_id={page_id}&limit=200")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    return sum(1 for item in items if item["permissions"].get("pdash_default_example") is True)


def test_fresh_home_has_default_examples(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    assert _default_example_count(admin_client, page_id) == len(DEFAULT_EXAMPLE_TYPES)


def test_clear_default_examples(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    assert _default_example_count(admin_client, page_id) == len(DEFAULT_EXAMPLE_TYPES)

    resp = admin_client.delete(f"/api/v1/pages/{page_id}/default-examples")
    assert resp.status_code == 200, resp.text
    assert resp.json()["cleared"] == len(DEFAULT_EXAMPLE_TYPES)
    assert _default_example_count(admin_client, page_id) == 0

    resp = admin_client.delete(f"/api/v1/pages/{page_id}/default-examples")
    assert resp.status_code == 200, resp.text
    assert resp.json()["cleared"] == 0


def test_deploy_default_examples(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    admin_client.delete(f"/api/v1/pages/{page_id}/default-examples")
    assert _default_example_count(admin_client, page_id) == 0

    resp = admin_client.post(f"/api/v1/pages/{page_id}/default-examples")
    assert resp.status_code == 200, resp.text
    assert resp.json()["deployed"] == len(DEFAULT_EXAMPLE_TYPES)

    modules_resp = admin_client.get(f"/api/v1/modules?page_id={page_id}&limit=200")
    assert modules_resp.status_code == 200, modules_resp.text
    items = modules_resp.json()["items"]
    assert len(items) == len(DEFAULT_EXAMPLE_TYPES)
    assert {item["type"] for item in items} == DEFAULT_EXAMPLE_TYPES
    for item in items:
        assert item["permissions"]["pdash_default_example"] is True
        assert item["permissions"]["seed_version"] == SEED_VERSION


def test_deploy_replaces_partial_default_examples(admin_client: TestClient) -> None:
    page_id = _home_page_id(admin_client)
    modules_resp = admin_client.get(f"/api/v1/modules?page_id={page_id}&limit=200")
    assert modules_resp.status_code == 200
    first_id = modules_resp.json()["items"][0]["id"]
    assert admin_client.delete(f"/api/v1/modules/{first_id}").status_code == 204
    assert _default_example_count(admin_client, page_id) == len(DEFAULT_EXAMPLE_TYPES) - 1

    resp = admin_client.post(f"/api/v1/pages/{page_id}/default-examples")
    assert resp.status_code == 200, resp.text
    assert resp.json()["deployed"] == len(DEFAULT_EXAMPLE_TYPES)
    assert _default_example_count(admin_client, page_id) == len(DEFAULT_EXAMPLE_TYPES)


def test_default_examples_endpoints_reject_non_home_page(admin_client: TestClient) -> None:
    page_id = _custom_page_id(admin_client)

    clear_resp = admin_client.delete(f"/api/v1/pages/{page_id}/default-examples")
    assert clear_resp.status_code == 400, clear_resp.text
    assert clear_resp.json()["code"] == "page.not_home"

    deploy_resp = admin_client.post(f"/api/v1/pages/{page_id}/default-examples")
    assert deploy_resp.status_code == 400, deploy_resp.text
    assert deploy_resp.json()["code"] == "page.not_home"
