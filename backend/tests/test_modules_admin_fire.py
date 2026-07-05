"""Tests for the admin-side `POST /api/v1/modules/{id}/fire` endpoint.

Admin firing bypasses the approval engine entirely (PLAN §0). The endpoint
should:

- 404 if the module doesn't exist.
- 400 if the module is the wrong type.
- Dispatch the target and stash a `last_result` on data.
- Audit-log the firing with target_kind=action_target.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from _phase3_helpers import home_page_id


def _create_target(client: TestClient, *, name: str, kind: str, config: dict) -> str:
    resp = client.post(
        "/api/v1/action-targets",
        json={"name": name, "kind": kind, "config": config, "mode": "sync"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_action_button(client: TestClient, *, target_id: str, page_id: str) -> str:
    resp = client.post(
        "/api/v1/modules",
        json={
            "type": "action_button",
            "page_id": page_id,
            "title": "Run",
            "data": {"label": "Run", "action_target_id": target_id},
            "config": {"confirm": False, "show_last_result": True},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_admin_fire_local_script_success(admin_client: TestClient) -> None:
    home_id = home_page_id(admin_client)
    tid = _create_target(
        admin_client,
        name="noop-true",
        kind="local_script",
        config={"command": "/usr/bin/env true", "timeout_seconds": 5},
    )
    mid = _create_action_button(admin_client, target_id=tid, page_id=home_id)

    resp = admin_client.post(f"/api/v1/modules/{mid}/fire", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["module_version"] >= 2  # version bumped from initial 1

    # The module now carries a last_result.
    after = admin_client.get(f"/api/v1/modules/{mid}").json()
    lr = after["data"].get("last_result")
    assert lr is not None
    assert lr["ok"] is True


def test_admin_fire_unknown_module_404(admin_client: TestClient) -> None:
    resp = admin_client.post("/api/v1/modules/mod_nope/fire", json={})
    assert resp.status_code == 404


def test_admin_fire_wrong_type_400(admin_client: TestClient) -> None:
    home_id = home_page_id(admin_client)
    # Create a markdown module
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": home_id,
            "title": "doc",
            "data": {"body": "hi"},
            "config": {},
        },
    )
    mid = resp.json()["id"]
    fire = admin_client.post(f"/api/v1/modules/{mid}/fire", json={})
    assert fire.status_code == 400
    assert fire.json()["code"] == "module.wrong_type"


def test_admin_fire_writes_audit_row(admin_client: TestClient) -> None:
    home_id = home_page_id(admin_client)
    tid = _create_target(
        admin_client,
        name="audit-true",
        kind="local_script",
        config={"command": "/usr/bin/env true"},
    )
    mid = _create_action_button(admin_client, target_id=tid, page_id=home_id)
    admin_client.post(f"/api/v1/modules/{mid}/fire", json={})
    log = admin_client.get(
        "/api/v1/activity-log?kind=fire_action_button"
    ).json()
    assert any(
        row.get("target_id") == tid for row in log["items"]
    ), json.dumps(log["items"], indent=2)
