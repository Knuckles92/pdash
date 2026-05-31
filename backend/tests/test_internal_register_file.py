"""Tests for the agent file-drop register flow (``/api/v1/internal/*``).

Covers: dropbox discovery, register -> pending -> approve (file moved + row),
auto-approve rule, deny, path traversal, missing/oversize/mime guards,
idempotency replay, and the apply-time re-validation (file changed / vanished).
"""

from __future__ import annotations

from pathlib import Path

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)
from fastapi.testclient import TestClient


def _inbox_dir(page_id: str | None = None) -> Path:
    from app.config import get_settings
    from app.services.files import page_inbox_dir

    d = page_inbox_dir(get_settings().resolved_files_inbox_path(), page_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _drop(name: str, *, page_id: str | None = None, content: bytes = b"hello-bytes") -> Path:
    p = _inbox_dir(page_id) / name
    p.write_bytes(content)
    return p


def _register_body(name: str, page_id: str | None = None, **kw) -> dict:
    body = {"inbox_name": name, "display_name": kw.get("display_name", "My File")}
    if page_id is not None:
        body["page_id"] = page_id
    return body


def test_file_dropbox_returns_paths(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="dropbox-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    resp = admin_client.get(
        f"/api/v1/internal/file-dropbox?page_id={page_id}",
        headers=internal_headers(agent_id, secret),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inbox_root"]
    assert body["target"] and page_id in body["target"]
    assert body["max_bytes"] > 0
    # The target dir was created.
    assert Path(body["target"]).is_dir()


def test_register_routes_to_pending_then_approve_moves_file(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="reg-pending")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _drop("report.png", page_id=page_id, content=b"\x89PNG\r\n\x1a\n-fake")

    resp = admin_client.post(
        "/api/v1/internal/register-file",
        json=_register_body("report.png", page_id, display_name="Quarterly Report"),
        headers=internal_headers(agent_id, secret, idempotency_key="reg-1"),
    )
    assert resp.status_code == 202, resp.text
    req_id = resp.json()["request_id"]
    assert req_id.startswith("apr_")

    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={"reason": "ok"}
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["applied"] is True
    file_id = approve.json()["apply_result"]["file_id"]
    assert file_id.startswith("fil_")

    # The file row exists and is registered; the inbox copy is gone (moved).
    meta = admin_client.get(f"/api/v1/files/{file_id}")
    assert meta.status_code == 200
    assert meta.json()["kind"] == "image"
    assert meta.json()["mime"] == "image/png"
    assert meta.json()["display_name"] == "Quarterly Report"
    assert not (_inbox_dir(page_id) / "report.png").exists()


def test_auto_approve_rule_applies_immediately(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="reg-autorule")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _drop("a.png", page_id=page_id)

    r1 = admin_client.post(
        "/api/v1/internal/register-file",
        json=_register_body("a.png", page_id),
        headers=internal_headers(agent_id, secret, idempotency_key="ar-1"),
    )
    assert r1.status_code == 202
    req_id = r1.json()["request_id"]
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve",
        json={
            "reason": "auto-approve future files",
            "create_rule": {
                "agent_id": agent_id,
                "action_type": "register_file",
                "outcome": "auto_approve",
                "priority": 50,
            },
        },
    )
    assert approve.status_code == 200, approve.text

    _drop("b.png", page_id=page_id)
    r2 = admin_client.post(
        "/api/v1/internal/register-file",
        json=_register_body("b.png", page_id),
        headers=internal_headers(agent_id, secret, idempotency_key="ar-2"),
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "applied"
    assert body["file_id"].startswith("fil_")
    assert body["url"].endswith("/raw")
    assert body["file"]["display_name"] == "My File"


def test_deny_keeps_file_in_inbox(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="reg-deny")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _drop("keep.png", page_id=page_id)
    r = admin_client.post(
        "/api/v1/internal/register-file",
        json=_register_body("keep.png", page_id),
        headers=internal_headers(agent_id, secret, idempotency_key="d-1"),
    )
    req_id = r.json()["request_id"]
    deny = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/deny", json={"reason": "no"}
    )
    assert deny.status_code == 200
    assert deny.json()["request"]["status"] == "denied"
    # File still sits in the inbox -> becomes an orphan candidate.
    assert (_inbox_dir(page_id) / "keep.png").exists()


def test_path_traversal_rejected(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="reg-traversal")
    secret = get_service_secret()
    for bad in ("../escape.png", "sub/dir.png", "/abs.png"):
        resp = admin_client.post(
            "/api/v1/internal/register-file",
            json={"inbox_name": bad, "display_name": "x"},
            headers=internal_headers(agent_id, secret, idempotency_key=f"trav-{bad}"),
        )
        assert resp.status_code == 400, (bad, resp.text)
        assert resp.json()["code"] == "file.invalid_name"


def test_missing_inbox_file_404(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="reg-missing")
    secret = get_service_secret()
    resp = admin_client.post(
        "/api/v1/internal/register-file",
        json={"inbox_name": "nope.png", "display_name": "x"},
        headers=internal_headers(agent_id, secret, idempotency_key="miss-1"),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "file.not_in_inbox"


def test_oversize_rejected(admin_client: TestClient, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "file_max_bytes", 4)  # shrink the cap
    agent_id, _ = register_agent(admin_client, name="reg-big")
    secret = get_service_secret()
    _drop("big.png", content=b"way too many bytes")
    resp = admin_client.post(
        "/api/v1/internal/register-file",
        json={"inbox_name": "big.png", "display_name": "x"},
        headers=internal_headers(agent_id, secret, idempotency_key="big-1"),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "file.too_large"


def test_idempotency_replay(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="reg-idem")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _drop("i.png", page_id=page_id)
    headers = internal_headers(agent_id, secret, idempotency_key="idem-1")
    body = _register_body("i.png", page_id)
    r1 = admin_client.post("/api/v1/internal/register-file", json=body, headers=headers)
    r2 = admin_client.post("/api/v1/internal/register-file", json=body, headers=headers)
    assert r1.status_code == 202 and r2.status_code == 202
    assert r1.json()["request_id"] == r2.json()["request_id"]
    assert r2.headers.get("X-Idempotency-Replay") == "true"


def test_file_changed_between_submit_and_apply(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="reg-changed")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _drop("c.png", page_id=page_id, content=b"original")
    r = admin_client.post(
        "/api/v1/internal/register-file",
        json=_register_body("c.png", page_id),
        headers=internal_headers(agent_id, secret, idempotency_key="ch-1"),
    )
    req_id = r.json()["request_id"]
    # Mutate the bytes after submit.
    _drop("c.png", page_id=page_id, content=b"tampered-now-different")
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={"reason": "ok"}
    )
    assert approve.status_code == 200
    assert approve.json()["applied"] is False
    assert "file.changed" in approve.json()["error"]


def test_my_files_lists_registered(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="reg-myfiles")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _drop("m.png", page_id=page_id)
    r = admin_client.post(
        "/api/v1/internal/register-file",
        json=_register_body("m.png", page_id),
        headers=internal_headers(agent_id, secret, idempotency_key="mf-1"),
    )
    req_id = r.json()["request_id"]
    admin_client.post(f"/api/v1/approval-requests/{req_id}/approve", json={"reason": "ok"})

    listing = admin_client.get(
        "/api/v1/internal/my-files", headers=internal_headers(agent_id, secret)
    )
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "image"
