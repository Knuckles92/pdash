"""Integration tests for seeded example pending approval requests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.seed_approvals import EXAMPLE_AGENT_DISPLAY_NAME, IDEMPOTENCY_PREFIX


def _login(client: TestClient, password: str) -> None:
    resp = client.post("/api/v1/auth/login", json={"password": password})
    assert resp.status_code == 200, resp.text


def test_fresh_db_seeds_example_pending_approvals(
    client: TestClient, initialized_db
) -> None:
    _, admin_password = initialized_db
    _login(client, admin_password)

    resp = client.get("/api/v1/approval-requests", params={"status": "pending", "limit": 200})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    examples = [
        item
        for item in items
        if (item.get("idempotency_key") or "").startswith(IDEMPOTENCY_PREFIX)
    ]
    assert len(examples) == 3
    actions = {item["action_type"] for item in examples}
    assert actions == {"create_module", "update_module_data", "update_module_config"}


def test_example_approvals_have_dashboard_previews(
    client: TestClient, initialized_db
) -> None:
    _, admin_password = initialized_db
    _login(client, admin_password)

    list_resp = client.get(
        "/api/v1/approval-requests", params={"status": "pending", "limit": 200}
    )
    examples = [
        item
        for item in list_resp.json()["items"]
        if (item.get("idempotency_key") or "").startswith(IDEMPOTENCY_PREFIX)
    ]
    create_req = next(i for i in examples if i["action_type"] == "create_module")
    update_req = next(i for i in examples if i["action_type"] == "update_module_data")

    create_detail = client.get(f"/api/v1/approval-requests/{create_req['id']}")
    assert create_detail.status_code == 200, create_detail.text
    create_preview = create_detail.json()["dashboard_preview"]
    assert create_preview is not None
    assert create_preview["highlight"]["change"] == "create"

    update_detail = client.get(f"/api/v1/approval-requests/{update_req['id']}")
    assert update_detail.status_code == 200, update_detail.text
    update_preview = update_detail.json()["dashboard_preview"]
    assert update_preview is not None
    assert update_preview["highlight"]["change"] == "update"


def test_fresh_db_seeds_example_demo_agent(client: TestClient, initialized_db) -> None:
    _, admin_password = initialized_db
    _login(client, admin_password)

    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200, resp.text
    names = {item["display_name"] for item in resp.json()["items"]}
    assert EXAMPLE_AGENT_DISPLAY_NAME in names
