"""Canvas page type + html module type (agent-controlled HTML pages).

Locks in the two surfaces (the ``canvas`` page type and the ``html`` module
type), the 400KB body cap, the agent-facing theme-token docs in the schema,
the ``type`` passthrough on ``propose-page``, and — critically — that html
content updates always **prompt** (the migration-seeded built-in rule outranks
the generic self-owned ``update_module_data`` auto-approve).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _phase3_helpers import get_service_secret, internal_headers, register_agent

VALID_HTML = "<!doctype html><html><head></head><body><h1>hi</h1></body></html>"


def _canvas_page_id(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/pages",
        json={"slug": "canvas", "name": "Canvas", "type": "canvas"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["type"] == "canvas"
    return resp.json()["id"]


def test_create_canvas_page(admin_client: TestClient) -> None:
    page_id = _canvas_page_id(admin_client)
    resp = admin_client.get(f"/api/v1/pages/{page_id}")
    assert resp.status_code == 200
    assert resp.json()["type"] == "canvas"


def test_html_module_round_trips(admin_client: TestClient) -> None:
    page_id = _canvas_page_id(admin_client)
    create = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "html",
            "page_id": page_id,
            "title": "Dashboard app",
            "data": {"html": VALID_HTML},
            "config": {"height_px": 800},
        },
    )
    assert create.status_code == 201, create.text
    mod = create.json()
    assert mod["type"] == "html"
    assert mod["data"]["html"] == VALID_HTML
    assert mod["config"]["height_px"] == 800


def test_html_module_rejects_oversize_body(admin_client: TestClient) -> None:
    page_id = _canvas_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "html",
            "page_id": page_id,
            "data": {"html": "x" * 400_001},
        },
    )
    assert resp.status_code >= 400


def test_html_module_rejects_extra_fields(admin_client: TestClient) -> None:
    page_id = _canvas_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "html",
            "page_id": page_id,
            "data": {"html": VALID_HTML, "bogus": 1},
        },
    )
    assert resp.status_code >= 400


def test_module_schema_documents_theme_tokens(admin_client: TestClient) -> None:
    # Agents learn the injected --pdash-* token contract via the html field
    # description served by the schema endpoint.
    resp = admin_client.get("/api/v1/module-schemas/html")
    assert resp.status_code == 200
    desc = resp.json()["data"]["properties"]["html"]["description"]
    assert "--pdash-accent" in desc
    assert "sandboxed iframe" in desc


def test_propose_page_type_canvas(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="canvas-bot")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/propose-page",
        json={"name": "Status Board", "slug": "status-board", "type": "canvas"},
        headers=internal_headers(agent_id, secret, idempotency_key="cv-1"),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"

    detail = admin_client.get(f"/api/v1/approval-requests/{body['request_id']}")
    assert detail.status_code == 200
    assert detail.json()["proposed_payload"]["type"] == "canvas"

    approve = admin_client.post(
        f"/api/v1/approval-requests/{body['request_id']}/approve", json={}
    )
    assert approve.status_code == 200
    assert approve.json()["applied"] is True

    pages = admin_client.get("/api/v1/pages").json()["items"]
    created = next(p for p in pages if p["slug"] == "status-board")
    assert created["type"] == "canvas"


def test_propose_page_type_defaults_agent(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="plain-bot")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/propose-page",
        json={"name": "Plain Workspace", "slug": "plain-ws"},
        headers=internal_headers(agent_id, secret, idempotency_key="cv-2"),
    )
    assert resp.status_code == 202, resp.text
    detail = admin_client.get(f"/api/v1/approval-requests/{resp.json()['request_id']}")
    assert detail.json()["proposed_payload"]["type"] == "agent"


def test_propose_page_rejects_other_types(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="sneaky-bot")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/propose-page",
        json={"name": "Sneaky", "slug": "sneaky", "type": "system"},
        headers=internal_headers(agent_id, secret, idempotency_key="cv-3"),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_decide_html_update_prompts_despite_self_ownership(initialized_db) -> None:
    # The 0010-seeded built-in rule (update_module_data + module_type=html →
    # prompt) is more specific than the generic self-owned auto-approve, so
    # agent HTML rewrites always reach the admin inbox by default.
    from app.approval.engine import DecisionRequest, decide, reset_cache_for_tests
    from app.db import get_sessionmaker

    reset_cache_for_tests()
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            html_decision = await decide(
                session,
                DecisionRequest(
                    action_type="update_module_data",
                    agent_id="agt_alpha",
                    module_type="html",
                    module_id="mod_self_owned",
                    page_id=None,
                    agent_owns_target=True,
                ),
            )
            assert html_decision.status == "prompt"
            assert html_decision.rule_id is not None

            # Regression guard: other types keep the self-owned auto-approve.
            md_decision = await decide(
                session,
                DecisionRequest(
                    action_type="update_module_data",
                    agent_id="agt_alpha",
                    module_type="markdown",
                    module_id="mod_self_owned",
                    page_id=None,
                    agent_owns_target=True,
                ),
            )
            assert md_decision.status == "auto_approve"
    finally:
        reset_cache_for_tests()


def test_agent_html_update_lands_pending(admin_client: TestClient) -> None:
    # End-to-end through the internal surface: create (prompt → approve), then
    # a data update on the agent's own html module must come back pending.
    agent_id, _ = register_agent(admin_client, name="html-bot")
    secret = get_service_secret()
    page_id = _canvas_page_id(admin_client)

    propose = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "html",
            "page_id": page_id,
            "title": "App",
            "data": {"html": VALID_HTML},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="cv-4"),
    )
    assert propose.status_code == 202, propose.text
    approve = admin_client.post(
        f"/api/v1/approval-requests/{propose.json()['request_id']}/approve", json={}
    )
    assert approve.status_code == 200
    module_id = approve.json()["request"]["target_id"]

    update = admin_client.post(
        "/api/v1/internal/update-module",
        json={
            "id": module_id,
            "patch": {"data": {"html": VALID_HTML.replace("hi", "v2")}},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="cv-5"),
    )
    assert update.status_code == 202, update.text
    assert update.json()["status"] == "pending"
