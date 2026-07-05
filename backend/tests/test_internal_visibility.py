"""Coverage for the agent visibility + self-diagnosis surface:
module-schemas, modules/{id}, pages, pages/{id}/render, module-health,
validate-module, structured invalid-payload errors, and the screenshot guard.
"""

from __future__ import annotations

import asyncio

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)
from fastapi.testclient import TestClient


def _make_module(
    admin_client: TestClient, page_id: str, owner_id: str, *, body: str = "hello"
) -> str:
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "title": "m",
            "data": {"body": body},
            "config": {},
            "owner_kind": "agent",
            "owner_id": owner_id,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _insert_broken_module(page_id: str, owner_id: str) -> str:
    """Insert a module whose stored data no longer validates (missing required
    markdown ``body``) — the kind of breakage a later schema change can cause.
    Bypasses the validating admin/agent write paths via a raw DB insert."""
    from sqlalchemy import text as sql_text

    from app.db import get_sessionmaker
    from app.ids import new_id
    from app.models import Module, utcnow_iso

    mod_id = new_id("mod")
    sm = get_sessionmaker()

    async def _go() -> None:
        async with sm() as session:
            await session.execute(sql_text("BEGIN IMMEDIATE"))
            now = utcnow_iso()
            session.add(
                Module(
                    id=mod_id,
                    type="markdown",
                    title="broken",
                    owner_kind="agent",
                    owner_id=owner_id,
                    page_id=page_id,
                    position=99,
                    grid=None,
                    permissions="{}",
                    data="{}",  # valid JSON, but invalid markdown (body required)
                    config="{}",
                    schema_version=1,
                    version=1,
                    created_at=now,
                    updated_at=now,
                    last_updated_by="test",
                )
            )
            await session.commit()

    asyncio.run(_go())
    return mod_id


def test_list_module_schemas(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="schemas")
    secret = get_service_secret()
    resp = admin_client.get(
        "/api/v1/internal/module-schemas", headers=internal_headers(agent_id, secret)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "markdown" in body["types"]
    types_in_items = {item["type"] for item in body["items"]}
    assert "markdown" in types_in_items
    assert len(body["items"]) == len(body["types"])


def test_get_module_by_id_owned_with_health(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="getmod")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    mod_id = _make_module(admin_client, page_id, agent_id)

    resp = admin_client.get(
        f"/api/v1/internal/modules/{mod_id}", headers=internal_headers(agent_id, secret)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == mod_id
    assert body["owned"] is True
    assert body["health"]["render_ok"] is True


def test_get_module_by_id_unowned_still_visible(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="viewer")
    other_id, _ = register_agent(admin_client, name="owner2")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    mod_id = _make_module(admin_client, page_id, other_id)

    resp = admin_client.get(
        f"/api/v1/internal/modules/{mod_id}", headers=internal_headers(agent_id, secret)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["owned"] is False


def test_get_module_by_id_not_found(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="missmod")
    secret = get_service_secret()
    resp = admin_client.get(
        "/api/v1/internal/modules/mod_does_not_exist",
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "module.not_found"


def test_list_pages_shows_home_with_counts(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pager")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _make_module(admin_client, page_id, agent_id)

    resp = admin_client.get(
        "/api/v1/internal/pages", headers=internal_headers(agent_id, secret)
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    home = next(p for p in items if p["slug"] == "home")
    assert home["module_count"] >= 1
    assert home["my_module_count"] >= 1


def test_render_page_structure_and_layout(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="render")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _make_module(admin_client, page_id, agent_id, body="one")
    _make_module(admin_client, page_id, agent_id, body="two")

    resp = admin_client.get(
        f"/api/v1/internal/pages/{page_id}/render",
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page"]["slug"] == "home"
    assert body["summary"]["total"] >= 2
    assert body["summary"]["broken"] == 0
    assert isinstance(body["layout"]["ascii"], str) and body["layout"]["ascii"]
    assert all(m["health"]["render_ok"] for m in body["modules"])


def test_render_page_detects_broken(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="renderbroken")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    broken_id = _insert_broken_module(page_id, agent_id)

    resp = admin_client.get(
        f"/api/v1/internal/pages/{page_id}/render",
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert broken_id in body["broken_module_ids"]
    assert body["summary"]["broken"] >= 1


def test_module_health_only_broken(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="health")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _make_module(admin_client, page_id, agent_id, body="fine")
    broken_id = _insert_broken_module(page_id, agent_id)

    resp = admin_client.get(
        "/api/v1/internal/module-health",
        params={"only_broken": "true"},
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    ids = {i["id"] for i in items}
    assert broken_id in ids
    broken = next(i for i in items if i["id"] == broken_id)
    assert broken["render_ok"] is False
    assert broken["errors"]
    assert broken["errors"][0]["section"] == "data"


def test_validate_module_ok(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="val-ok")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/validate-module",
        json={"type": "markdown", "data": {"body": "hi"}, "config": {}},
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["type_known"] is True
    assert body["errors"] == []


def test_validate_module_reports_errors(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="val-err")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/validate-module",
        json={"type": "markdown", "data": {}, "config": {}},
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert any(e["section"] == "data" and "body" in e["loc"] for e in body["errors"])


def test_validate_module_unknown_type(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="val-unknown")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/validate-module",
        json={"type": "nope", "data": {}, "config": {}},
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["type_known"] is False


def test_propose_module_invalid_payload_has_structured_errors(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="badpropose")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={"type": "markdown", "page_id": page_id, "data": {}, "config": {}},
        headers=internal_headers(agent_id, secret, idempotency_key="bad-1"),
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "module.invalid_payload"
    assert any(e["section"] == "data" for e in body["errors"])


def test_screenshot_unavailable_without_service(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="shot")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.get(
        f"/api/v1/internal/pages/{page_id}/screenshot",
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 501, resp.text
    assert resp.json()["code"] == "screenshot.unavailable"


def test_pagination_no_gaps_across_boundaries(admin_client: TestClient) -> None:
    """Cursor pagination must include every row — the look-ahead row at a page
    boundary must not be skipped (regression for the next_cursor off-by-one)."""
    agent_id, _ = register_agent(admin_client, name="paginate")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    created = {
        _make_module(admin_client, page_id, agent_id, body=f"m{i}") for i in range(7)
    }

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # safety bound
        params: dict[str, str | int] = {"limit": 3}
        if cursor:
            params["cursor"] = cursor
        resp = admin_client.get(
            "/api/v1/internal/my-modules",
            params=params,
            headers=internal_headers(agent_id, secret),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        seen.extend(m["id"] for m in body["items"])
        cursor = body["next_cursor"]
        if not cursor:
            break

    assert len(seen) == len(set(seen)), "pagination returned duplicates"
    assert created.issubset(set(seen)), "pagination skipped rows at a page boundary"


def test_screenshot_scoped_session_is_read_only(
    client: TestClient, signing_secret: str
) -> None:
    """The audience-scoped cookie minted for screenshots may render (GET) but
    must never authorize a state-changing admin request."""
    import time as _time

    from app.auth.cookies import SessionPayload, sign_session

    now = int(_time.time())
    token = sign_session(
        SessionPayload(
            user_id="admin", issued_at=now, expires_at=now + 120, audience="screenshot"
        ),
        signing_secret,
    )
    client.cookies.set("session", token)

    # Reads (what a dashboard render needs) are allowed.
    read = client.get("/api/v1/pages")
    assert read.status_code == 200, read.text

    # State-changing requests are refused before they can touch state.
    write = client.post(
        "/api/v1/pages",
        json={"name": "Nope", "slug": "nope"},
        headers={"X-CSRF-Token": "x"},
    )
    assert write.status_code == 403, write.text
    assert write.json()["code"] == "auth.read_only_session"
