"""Tests for the per-page agent access endpoints.

``GET  /api/v1/pages/{page_id}/agent-access``
``PUT  /api/v1/pages/{page_id}/agent-access/{agent_id}``

The PUT persists a managed set of approval rules (one per module action type,
scoped to agent+page); the GET reads the level back shape-based. The
end-to-end tests drive the internal propose-module endpoint to prove the
managed rules actually change engine decisions.
"""

from __future__ import annotations

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)
from fastapi.testclient import TestClient

MANAGED_ACTION_TYPES = {
    "create_module",
    "update_module_data",
    "update_module_config",
    "update_module_meta",
    "delete_module",
}


def _access_of(admin_client: TestClient, page_id: str, agent_id: str) -> dict:
    resp = admin_client.get(f"/api/v1/pages/{page_id}/agent-access")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    return next(item for item in items if item["agent_id"] == agent_id)


def _set_access(
    admin_client: TestClient, page_id: str, agent_id: str, access: str
) -> dict:
    resp = admin_client.put(
        f"/api/v1/pages/{page_id}/agent-access/{agent_id}",
        json={"access": access},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _page_rules(admin_client: TestClient, page_id: str) -> list[dict]:
    resp = admin_client.get(f"/api/v1/approval-rules?page_id={page_id}")
    assert resp.status_code == 200
    return resp.json()["items"]


def _propose_module(
    admin_client: TestClient,
    agent_id: str,
    page_id: str,
    *,
    idem: str,
) -> dict:
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "title": "access-test",
            "data": {"body": "# hi"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key=idem),
    )
    # 200/201/202 applied|pending; 403 denied_by_rule.
    assert resp.status_code in (200, 201, 202, 403), resp.text
    return resp.json()


def test_get_lists_agents_with_default_access(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pa-default")
    page_id = home_page_id(admin_client)
    item = _access_of(admin_client, page_id, agent_id)
    assert item["access"] == "default"
    assert item["module_count"] == 0
    assert item["custom_rule_count"] == 0
    assert item["display_name"] == "pa-default"
    assert item["status"] == "active"


def test_get_unknown_page_404(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/pages/pg_nope/agent-access")
    assert resp.status_code == 404
    assert resp.json()["code"] == "page.not_found"


def test_put_unknown_agent_404(admin_client: TestClient) -> None:
    page_id = home_page_id(admin_client)
    resp = admin_client.put(
        f"/api/v1/pages/{page_id}/agent-access/agt_nope",
        json={"access": "free"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "agent.not_found"


def test_free_creates_managed_rules_and_auto_approves(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="pa-free")
    page_id = home_page_id(admin_client)

    item = _set_access(admin_client, page_id, agent_id, "free")
    assert item["access"] == "free"

    rules = [r for r in _page_rules(admin_client, page_id) if r["agent_id"] == agent_id]
    assert {r["action_type"] for r in rules} == MANAGED_ACTION_TYPES
    assert {r["outcome"] for r in rules} == {"auto_approve"}
    assert all(r["module_type"] is None and r["module_id"] is None for r in rules)
    assert all(r["owner_scope"] == "any" for r in rules)
    assert all(not r["is_builtin"] for r in rules)

    # create_module normally prompts (built-in rule); with free access it applies.
    body = _propose_module(admin_client, agent_id, page_id, idem="pa-free-1")
    assert body["status"] == "applied", body


def test_blocked_denies_module_writes(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pa-blocked")
    page_id = home_page_id(admin_client)

    item = _set_access(admin_client, page_id, agent_id, "blocked")
    assert item["access"] == "blocked"

    body = _propose_module(admin_client, agent_id, page_id, idem="pa-blocked-1")
    assert body["status"] == "denied_by_rule", body


def test_default_removes_managed_rules_and_restores_prompt(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="pa-reset")
    page_id = home_page_id(admin_client)

    _set_access(admin_client, page_id, agent_id, "free")
    item = _set_access(admin_client, page_id, agent_id, "default")
    assert item["access"] == "default"

    rules = [r for r in _page_rules(admin_client, page_id) if r["agent_id"] == agent_id]
    assert rules == []

    body = _propose_module(admin_client, agent_id, page_id, idem="pa-reset-1")
    assert body["status"] == "pending", body


def test_switch_free_to_blocked_replaces_set(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pa-switch")
    page_id = home_page_id(admin_client)

    _set_access(admin_client, page_id, agent_id, "free")
    item = _set_access(admin_client, page_id, agent_id, "blocked")
    assert item["access"] == "blocked"

    rules = [r for r in _page_rules(admin_client, page_id) if r["agent_id"] == agent_id]
    assert len(rules) == len(MANAGED_ACTION_TYPES)
    assert {r["outcome"] for r in rules} == {"deny"}


def test_disabled_managed_rule_reads_as_custom(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pa-custom")
    page_id = home_page_id(admin_client)

    _set_access(admin_client, page_id, agent_id, "free")
    rules = [r for r in _page_rules(admin_client, page_id) if r["agent_id"] == agent_id]
    disable = admin_client.patch(
        f"/api/v1/approval-rules/{rules[0]['id']}", json={"enabled": False}
    )
    assert disable.status_code == 200

    item = _access_of(admin_client, page_id, agent_id)
    assert item["access"] == "custom"


def test_narrow_rule_counts_as_custom_but_keeps_level(
    admin_client: TestClient,
) -> None:
    agent_id, _ = register_agent(admin_client, name="pa-narrow")
    page_id = home_page_id(admin_client)

    _set_access(admin_client, page_id, agent_id, "free")
    created = admin_client.post(
        "/api/v1/approval-rules",
        json={
            "agent_id": agent_id,
            "action_type": "update_module_data",
            "page_id": page_id,
            "module_type": "markdown",
            "outcome": "deny",
        },
    )
    assert created.status_code == 201, created.text

    item = _access_of(admin_client, page_id, agent_id)
    assert item["access"] == "free"
    assert item["custom_rule_count"] == 1

    # Resetting to default only removes the managed set; the narrow rule stays.
    item = _set_access(admin_client, page_id, agent_id, "default")
    assert item["access"] == "default"
    assert item["custom_rule_count"] == 1


def test_module_count_reflects_agent_modules(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="pa-count")
    page_id = home_page_id(admin_client)

    _set_access(admin_client, page_id, agent_id, "free")
    body = _propose_module(admin_client, agent_id, page_id, idem="pa-count-1")
    assert body["status"] == "applied", body

    item = _access_of(admin_client, page_id, agent_id)
    assert item["module_count"] == 1
