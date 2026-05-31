"""Tests for the admin approve+rule flow and approval-rules CRUD."""

from __future__ import annotations

from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)


def _propose(admin_client: TestClient, agent_id: str, secret: str, page_id: str, idem: str, body: str = "hi"):
    return admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": body},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key=idem),
    )


def test_list_default_rules_seeded(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/approval-rules?limit=200")
    assert resp.status_code == 200
    items = resp.json()["items"]
    action_types = {r["action_type"] for r in items if r["is_builtin"]}
    # Spec lists 9 distinct action_types in default rules (with self/other for
    # update_module_data being two rows under the same action_type).
    expected = {
        "update_module_data",
        "update_module_config",
        "update_module_meta",
        "create_module",
        "delete_module",
        "create_page",
        "delete_page",
        "fire_action_button",
    }
    assert expected <= action_types


def test_list_rules_filters_by_page_id(admin_client: TestClient) -> None:
    home_id = home_page_id(admin_client)
    page_resp = admin_client.post(
        "/api/v1/pages",
        json={"slug": "rules-filter-page", "name": "Rules Filter"},
    )
    assert page_resp.status_code == 201, page_resp.text
    other_page_id = page_resp.json()["id"]

    home_rule = admin_client.post(
        "/api/v1/approval-rules",
        json={
            "action_type": "create_module",
            "page_id": home_id,
            "outcome": "auto_approve",
            "priority": 10,
        },
    )
    assert home_rule.status_code == 201, home_rule.text
    home_rule_id = home_rule.json()["rule"]["id"]
    other_rule = admin_client.post(
        "/api/v1/approval-rules",
        json={
            "action_type": "create_module",
            "page_id": other_page_id,
            "outcome": "deny",
            "priority": 11,
        },
    )
    assert other_rule.status_code == 201, other_rule.text
    other_rule_id = other_rule.json()["rule"]["id"]
    global_rule = admin_client.post(
        "/api/v1/approval-rules",
        json={
            "action_type": "create_module",
            "outcome": "prompt",
            "priority": 12,
        },
    )
    assert global_rule.status_code == 201, global_rule.text
    global_rule_id = global_rule.json()["rule"]["id"]

    resp = admin_client.get(f"/api/v1/approval-rules?page_id={home_id}&limit=200")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    ids = {r["id"] for r in items}

    assert home_rule_id in ids
    assert other_rule_id not in ids
    assert global_rule_id not in ids
    assert all(r["page_id"] == home_id for r in items)

    cleared = admin_client.patch(
        f"/api/v1/approval-rules/{home_rule_id}",
        json={"page_id": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["page_id"] is None

    resp = admin_client.get(f"/api/v1/approval-rules?page_id={home_id}&limit=200")
    assert resp.status_code == 200, resp.text
    ids = {r["id"] for r in resp.json()["items"]}
    assert home_rule_id not in ids


def test_create_custom_rule_invalidates_cache(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="cache-invalidate")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # Add a rule that auto-approves create_module for this agent.
    resp = admin_client.post(
        "/api/v1/approval-rules",
        json={
            "agent_id": agent_id,
            "action_type": "create_module",
            "outcome": "auto_approve",
            "priority": 10,
        },
    )
    assert resp.status_code == 201, resp.text

    # Now a propose should auto-apply.
    r = _propose(admin_client, agent_id, secret, page_id, idem="cache-1")
    assert r.status_code == 200
    assert r.json()["status"] == "applied"


def test_create_rule_with_apply_to_pending(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="retro-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # Three pending proposals first.
    pending_ids = []
    for i in range(3):
        r = _propose(admin_client, agent_id, secret, page_id, idem=f"retro-{i}", body=f"body-{i}")
        assert r.status_code == 202
        pending_ids.append(r.json()["request_id"])

    # Create a rule that auto-approves all create_module from this agent +
    # apply to pending in the same transaction.
    rule_resp = admin_client.post(
        "/api/v1/approval-rules",
        json={
            "agent_id": agent_id,
            "action_type": "create_module",
            "outcome": "auto_approve",
            "priority": 10,
            "apply_to_pending": True,
        },
    )
    assert rule_resp.status_code == 201, rule_resp.text
    assert rule_resp.json()["applied_to_pending"] == 3

    # All three should now be applied.
    for rid in pending_ids:
        r = admin_client.get(f"/api/v1/approval-requests/{rid}")
        assert r.json()["status"] == "applied"


def test_approve_with_create_rule_atomically(admin_client: TestClient) -> None:
    """Single approve call: applies + inserts the new rule in one transaction."""
    agent_id, _ = register_agent(admin_client, name="approve-with-rule")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    r1 = _propose(admin_client, agent_id, secret, page_id, idem="awr-1")
    req_id = r1.json()["request_id"]
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve",
        json={
            "reason": "good agent",
            "create_rule": {
                "agent_id": agent_id,
                "action_type": "create_module",
                "module_type": "markdown",
                "outcome": "auto_approve",
                "priority": 10,
            },
        },
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["applied"] is True
    assert "rule" in approve.json()

    # Confirm rule list contains it
    lst = admin_client.get(f"/api/v1/approval-rules?agent_id={agent_id}")
    rule_ids = {r["id"] for r in lst.json()["items"]}
    assert approve.json()["rule"]["id"] in rule_ids


def test_disable_builtin_rule_via_update(admin_client: TestClient) -> None:
    """A built-in rule can be disabled but not have its scope altered."""
    rules = admin_client.get("/api/v1/approval-rules?limit=200").json()["items"]
    # Pick a built-in with a 'prompt' outcome so flipping to 'auto_approve' is
    # actually a change (some built-ins are already auto_approve).
    builtin = next(r for r in rules if r["is_builtin"] and r["outcome"] == "prompt")
    rid = builtin["id"]
    # Disabling is fine
    r = admin_client.patch(
        f"/api/v1/approval-rules/{rid}", json={"enabled": False}
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    # Changing the outcome is not fine
    r = admin_client.patch(
        f"/api/v1/approval-rules/{rid}", json={"outcome": "auto_approve"}
    )
    assert r.status_code in (403, 400)


def test_delete_builtin_rule_forbidden(admin_client: TestClient) -> None:
    rules = admin_client.get("/api/v1/approval-rules?limit=200").json()["items"]
    builtin = next(r for r in rules if r["is_builtin"])
    resp = admin_client.delete(f"/api/v1/approval-rules/{builtin['id']}")
    assert resp.status_code == 403


def test_rule_preview_dry_run(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="preview-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    # Two pending requests
    _propose(admin_client, agent_id, secret, page_id, idem="prev-a")
    _propose(admin_client, agent_id, secret, page_id, idem="prev-b", body="other")

    rule_resp = admin_client.post(
        "/api/v1/approval-rules",
        json={
            "agent_id": agent_id,
            "action_type": "create_module",
            "outcome": "auto_approve",
            "priority": 10,
            # Don't apply retroactively
            "apply_to_pending": False,
        },
    )
    rid = rule_resp.json()["rule"]["id"]

    preview = admin_client.post(f"/api/v1/approval-rules/{rid}/preview?limit=100")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["matched"] >= 2
    assert body["scanned"] >= 2


def test_bulk_decide(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="bulk-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    # Three pending
    ids = []
    for i in range(3):
        r = _propose(admin_client, agent_id, secret, page_id, idem=f"bulk-{i}")
        ids.append(r.json()["request_id"])

    # Approve two, deny one
    resp = admin_client.post(
        "/api/v1/approval-requests/bulk-decide",
        json={
            "decisions": [
                {"id": ids[0], "decision": "approve"},
                {"id": ids[1], "decision": "deny"},
                {"id": ids[2], "decision": "approve"},
            ]
        },
    )
    assert resp.status_code == 200
    statuses = {item["id"]: item["status"] for item in resp.json()["results"]}
    assert statuses[ids[0]] == "applied"
    assert statuses[ids[1]] == "denied"
    assert statuses[ids[2]] == "applied"


def test_get_request_with_diff_preview(admin_client: TestClient) -> None:
    """Update requests get a per-key shallow diff against the live module."""
    agent_id, _ = register_agent(admin_client, name="diff-preview")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    # Create a module owned by another principal so the agent's update goes to prompt.
    mod_resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "old"},
            "config": {},
            "owner_kind": "user",
            "owner_id": "admin",
        },
    )
    mod_id = mod_resp.json()["id"]

    upd = admin_client.post(
        "/api/v1/internal/update-module",
        json={"id": mod_id, "patch": {"data": {"body": "new"}}},
        headers=internal_headers(agent_id, secret, idempotency_key="diff-1"),
    )
    assert upd.status_code == 202
    req_id = upd.json()["request_id"]

    detail = admin_client.get(f"/api/v1/approval-requests/{req_id}")
    assert detail.status_code == 200
    diff = detail.json()["diff_preview"]
    assert diff is not None
    assert "data" in diff
    assert diff["data"]["body"] == {"before": "old", "after": "new"}
