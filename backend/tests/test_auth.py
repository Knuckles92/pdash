"""Auth tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"password": "wrong"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "auth.invalid_credentials"
    assert resp.headers.get("content-type", "").startswith("application/problem+json")


def test_login_right_password_returns_200_and_sets_cookies(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"password": "test1234"})
    assert resp.status_code == 200
    assert "session" in client.cookies
    assert "csrf_token" in client.cookies


def test_me_works_with_session(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"password": "test1234"})
    assert resp.status_code == 200
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "admin"


def test_me_unauthenticated_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "auth.required"


def test_logout_clears_session(client: TestClient) -> None:
    client.post("/api/v1/auth/login", json={"password": "test1234"})
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    # After logout, /me should 401.
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_csrf_enforced_on_state_changing(admin_client: TestClient) -> None:
    """A POST without X-CSRF-Token header should be rejected."""
    bare = admin_client
    # Strip the X-CSRF-Token we set in admin_client fixture.
    bare.headers.pop("X-CSRF-Token", None)
    resp = bare.post("/api/v1/pages", json={
        "slug": "foo",
        "name": "Foo",
        "kind": "custom",
    })
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.csrf"
