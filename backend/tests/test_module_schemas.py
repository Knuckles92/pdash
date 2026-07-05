"""Module schema endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

EXPECTED_TYPES = {
    "markdown",
    "key_value",
    "table",
    "timeseries",
    "log_stream",
    "link_list",
    "iframe",
    "action_button",
    "notification",
    "file",
    "sticky_note",
    "progress",
    "html",
}


def test_list_all_schemas_returns_all_types(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/module-schemas")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["types"]) == EXPECTED_TYPES
    assert len(body["schemas"]) == len(EXPECTED_TYPES)
    for entry in body["schemas"]:
        assert "type" in entry
        assert "data" in entry
        assert "config" in entry
        assert entry["data_schema"] == entry["data"]
        assert entry["config_schema"] == entry["config"]
        # Each data/config should be a JSON-schema-shaped dict
        data_schema = entry["data"]
        assert isinstance(data_schema, dict)
        assert data_schema.get("type") in {"object", None} or "$ref" in data_schema or "properties" in data_schema
        config_schema = entry["config"]
        assert isinstance(config_schema, dict)
        assert "appearance" in config_schema.get("properties", {})


def test_each_type_individually_fetchable(admin_client: TestClient) -> None:
    for t in EXPECTED_TYPES:
        resp = admin_client.get(f"/api/v1/module-schemas/{t}")
        assert resp.status_code == 200, f"{t} failed: {resp.status_code}"
        body = resp.json()
        assert body["type"] == t
        assert "data" in body
        assert "config" in body
        assert "data_schema" in body
        assert "config_schema" in body


def test_unknown_type_404(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/module-schemas/totally-fake")
    assert resp.status_code == 404
    assert resp.json()["code"] == "module_schema.not_found"


def test_schemas_require_session(client: TestClient) -> None:
    resp = client.get("/api/v1/module-schemas")
    assert resp.status_code == 401
