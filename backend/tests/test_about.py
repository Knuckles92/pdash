"""About endpoint."""

from fastapi.testclient import TestClient


def test_about_requires_session(client: TestClient) -> None:
    assert client.get("/api/v1/about").status_code == 401


def test_about_returns_version(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/about")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "0.1.0"
