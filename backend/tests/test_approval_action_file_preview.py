"""Tests for action + file previews on approval request detail.

Parity with the dashboard preview: fire_action_button gets an ``action_preview``
(target + effective payload) and register_file gets a ``file_preview``
(metadata), each keyed off the request's action_type.
"""

from __future__ import annotations

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)
from fastapi.testclient import TestClient

from app.services.redact import REDACTED


def _detail(admin_client: TestClient, request_id: str) -> dict:
    resp = admin_client.get(f"/api/v1/approval-requests/{request_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_webhook_target(admin_client: TestClient, *, name: str, config: dict) -> str:
    resp = admin_client.post(
        "/api/v1/action-targets",
        json={"name": name, "kind": "webhook", "config": config, "mode": "sync"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_action_preview_webhook(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="action-preview")
    secret = get_service_secret()
    tid = _create_webhook_target(
        admin_client,
        name="deploy-hook",
        config={"url": "https://hooks.lan/deploy", "method": "post"},
    )

    # fire_action_button defaults to prompt -> stays pending, no real HTTP call.
    r = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid, "payload": {"hello": "world"}},
        headers=internal_headers(agent_id, secret, idempotency_key="ap-1"),
    )
    assert r.status_code == 202, r.text
    req_id = r.json()["request_id"]

    detail = _detail(admin_client, req_id)
    preview = detail["action_preview"]
    assert preview is not None
    assert preview["target"]["name"] == "deploy-hook"
    assert preview["target"]["kind"] == "webhook"
    assert preview["target"]["enabled"] is True
    assert preview["destination"] == "POST https://hooks.lan/deploy"
    assert preview["payload"] == {"hello": "world"}
    assert preview["uses_target_default"] is False
    # Only the matching preview is populated.
    assert detail["dashboard_preview"] is None
    assert detail["file_preview"] is None


def test_action_preview_uses_target_default_and_redacts_secrets(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="action-default")
    secret = get_service_secret()
    tid = _create_webhook_target(
        admin_client,
        name="secret-hook",
        config={
            "url": "https://hooks.lan/secret",
            "default_payload": {"token": "super-secret", "ok": True},
        },
    )

    # No payload -> webhook falls back to the target's default_payload.
    r = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid},
        headers=internal_headers(agent_id, secret, idempotency_key="ap-2"),
    )
    assert r.status_code == 202, r.text
    req_id = r.json()["request_id"]

    preview = _detail(admin_client, req_id)["action_preview"]
    assert preview["uses_target_default"] is True
    assert preview["payload"]["ok"] is True
    assert preview["payload"]["token"] == REDACTED


def test_file_preview(admin_client: TestClient) -> None:
    from app.config import get_settings
    from app.services.files import page_inbox_dir

    agent_id, _ = register_agent(admin_client, name="file-preview")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    inbox = page_inbox_dir(get_settings().resolved_files_inbox_path(), page_id)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "report.png").write_bytes(b"\x89PNG\r\n\x1a\n-fake")

    r = admin_client.post(
        "/api/v1/internal/register-file",
        json={
            "inbox_name": "report.png",
            "display_name": "Quarterly Report",
            "page_id": page_id,
            "purpose": "Q3 summary",
        },
        headers=internal_headers(agent_id, secret, idempotency_key="fp-1"),
    )
    assert r.status_code == 202, r.text
    req_id = r.json()["request_id"]

    detail = _detail(admin_client, req_id)
    preview = detail["file_preview"]
    assert preview is not None
    assert preview["display_name"] == "Quarterly Report"
    assert preview["inbox_name"] == "report.png"
    assert preview["kind"] == "image"
    assert preview["mime"] == "image/png"
    assert preview["size_bytes"] > 0
    assert preview["purpose"] == "Q3 summary"
    assert preview["sha256"]
    assert preview["page"]["id"] == page_id
    # Only the matching preview is populated.
    assert detail["dashboard_preview"] is None
    assert detail["action_preview"] is None
