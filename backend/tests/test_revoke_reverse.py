"""Tests for ``POST /api/v1/approval-rules/{id}/revoke?reverse_decisions=true``.

Phase 6: when revoking a rule with ``reverse_decisions=true``, scan the last
24h of applied auto-approved requests decided by that rule and roll them
back where possible:

- ``create_module`` → soft-delete the module.
- ``delete_module`` → undelete the module.
- ``update_module_*`` → skip with "cannot auto-revert update".
- ``create_page``    → soft-delete the page.
- ``delete_page``    → undelete the page.
- ``fire_action_button`` → skip with "cannot reverse executed actions".
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi.testclient import TestClient


def _create_auto_approve_rule(
    admin_client: TestClient,
    *,
    agent_id: str = "*",
    action_type: str = "create_module",
) -> str:
    body = {
        "agent_id": agent_id,
        "action_type": action_type,
        "owner_scope": "any",
        "outcome": "auto_approve",
        "priority": 1,  # win over the built-in prompt rule
        "enabled": True,
    }
    resp = admin_client.post("/api/v1/approval-rules", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["rule"]["id"]


def _make_pending_propose_module(
    admin_client: TestClient, *, idem: str
) -> tuple[str, str]:
    """Returns (request_id, target_module_id) for a freshly auto-applied create."""
    from _phase3_helpers import (
        get_service_secret,
        home_page_id,
        internal_headers,
        register_agent,
    )

    agent_id, _ = register_agent(admin_client, name=f"revoke-agt-{idem}")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": idem},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key=idem),
    )
    assert resp.status_code == 200, resp.text  # applied via the new rule
    return resp.json()["request_id"], resp.json()["module_id"]


def test_revoke_without_flag_does_not_revert(admin_client: TestClient) -> None:
    rule_id = _create_auto_approve_rule(admin_client)
    _req_id, mod_id = _make_pending_propose_module(admin_client, idem="r1")
    resp = admin_client.post(f"/api/v1/approval-rules/{rule_id}/revoke")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reversed_count"] == 0
    assert body["skipped_count"] == 0
    # Module should still be alive.
    mod = admin_client.get(f"/api/v1/modules/{mod_id}")
    assert mod.status_code == 200
    assert mod.json()["deleted_at"] is None


def test_revoke_reverse_soft_deletes_created_module(
    admin_client: TestClient,
) -> None:
    rule_id = _create_auto_approve_rule(admin_client)
    _req_id, mod_id = _make_pending_propose_module(admin_client, idem="r2")

    resp = admin_client.post(
        f"/api/v1/approval-rules/{rule_id}/revoke?reverse_decisions=true"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reversed_count"] >= 1
    # Find detail for our module
    matching = [d for d in body["details"] if d["target_id"] == mod_id]
    assert matching, body
    assert matching[0]["status"] == "reverted"
    # Module is now soft-deleted; admin GET returns 404.
    mod = admin_client.get(f"/api/v1/modules/{mod_id}")
    assert mod.status_code == 404


def test_revoke_reverse_skips_update_with_reason(
    admin_client: TestClient,
) -> None:
    """An auto-approved update_module_data should be skipped on revoke,
    because we have no canonical pre-image to restore.
    """
    from _phase3_helpers import (
        get_service_secret,
        home_page_id,
        internal_headers,
        register_agent,
    )

    agent_id, _ = register_agent(admin_client, name="update-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # Step 1: create the module via the agent so the agent OWNS it (the
    # built-in self-owner rule auto-approves data updates). We also create
    # our explicit auto-approve rule on update_module_data so its decisions
    # are tagged to that rule.
    create = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "v0"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="upd-create"),
    )
    # The default rule prompts on create, so we approve it manually here.
    if create.status_code == 202:
        req_id = create.json()["request_id"]
        approve = admin_client.post(
            f"/api/v1/approval-requests/{req_id}/approve", json={}
        )
        assert approve.status_code == 200, approve.text
        # The module id is on the apply result.
        mod_id = approve.json()["apply_result"]["module_id"]
    else:
        mod_id = create.json()["module_id"]

    rule_id = _create_auto_approve_rule(
        admin_client, action_type="update_module_data", agent_id=agent_id
    )

    upd = admin_client.post(
        "/api/v1/internal/update-module",
        json={
            "id": mod_id,
            "patch": {"data": {"body": "v1"}},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="upd-r"),
    )
    assert upd.status_code == 200, upd.text

    resp = admin_client.post(
        f"/api/v1/approval-rules/{rule_id}/revoke?reverse_decisions=true"
    )
    body = resp.json()
    matching = [d for d in body["details"] if d["target_id"] == mod_id]
    assert matching
    assert matching[0]["status"] == "skipped"
    assert "cannot auto-revert update" in matching[0]["detail"]
    assert body["skipped_count"] >= 1


def test_revoke_reverse_undeletes_for_delete_module(
    admin_client: TestClient,
) -> None:
    """An auto-approved delete_module should be undone (deleted_at = NULL)."""
    from _phase3_helpers import (
        get_service_secret,
        home_page_id,
        internal_headers,
        register_agent,
    )

    # Create the module first.
    page_id = home_page_id(admin_client)
    create = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "to delete"},
            "config": {},
        },
    )
    mod_id = create.json()["id"]

    agent_id, _ = register_agent(admin_client, name="del-agent")
    secret = get_service_secret()
    rule_id = _create_auto_approve_rule(
        admin_client, action_type="delete_module"
    )

    delete = admin_client.post(
        "/api/v1/internal/delete-module",
        json={"id": mod_id},
        headers=internal_headers(agent_id, secret, idempotency_key="del-r"),
    )
    assert delete.status_code == 200, delete.text
    # Module is now soft-deleted.
    assert admin_client.get(f"/api/v1/modules/{mod_id}").status_code == 404

    resp = admin_client.post(
        f"/api/v1/approval-rules/{rule_id}/revoke?reverse_decisions=true"
    )
    body = resp.json()
    assert body["reversed_count"] >= 1
    matching = [d for d in body["details"] if d["target_id"] == mod_id]
    assert matching and matching[0]["status"] == "reverted"
    # Module should be alive again.
    assert admin_client.get(f"/api/v1/modules/{mod_id}").status_code == 200


def test_revoke_reverse_writes_audit_per_reversal(
    admin_client: TestClient,
) -> None:
    rule_id = _create_auto_approve_rule(admin_client)
    _req_id, mod_id = _make_pending_propose_module(admin_client, idem="r4")
    admin_client.post(
        f"/api/v1/approval-rules/{rule_id}/revoke?reverse_decisions=true"
    )
    # The activity_log should contain a revoke_decision_reverse row.
    rows = admin_client.get(
        "/api/v1/activity-log?kind=revoke_decision_reverse&limit=50"
    ).json()["items"]
    assert rows
    target_ids = {r["target_id"] for r in rows}
    assert mod_id in target_ids


def test_revoke_reverse_only_matches_rows_decided_by_this_rule(
    admin_client: TestClient,
) -> None:
    """Two rules; revoke one — the other's decisions should not be touched."""
    rule_a = _create_auto_approve_rule(admin_client)
    _, mod_a = _make_pending_propose_module(admin_client, idem="ra")

    # Disable rule A so we can register a new one with the same action_type.
    admin_client.patch(
        f"/api/v1/approval-rules/{rule_a}",
        json={"enabled": False},
    )
    rule_b = _create_auto_approve_rule(admin_client)
    _, mod_b = _make_pending_propose_module(admin_client, idem="rb")

    # Revoke only rule A; only mod_a should be soft-deleted.
    resp = admin_client.post(
        f"/api/v1/approval-rules/{rule_a}/revoke?reverse_decisions=true"
    )
    body = resp.json()
    touched = {d["target_id"] for d in body["details"] if d["status"] == "reverted"}
    assert mod_a in touched
    assert mod_b not in touched
    # mod_b should still exist.
    assert admin_client.get(f"/api/v1/modules/{mod_b}").status_code == 200
