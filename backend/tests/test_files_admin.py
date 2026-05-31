"""Tests for the admin file surface: list/reconcile, inbox delete, manual
register, delete, and store-orphan detection."""

from __future__ import annotations

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)
from fastapi.testclient import TestClient


def _drop(name: str, *, page_id: str | None = None, content: bytes = b"x") -> None:
    from app.config import get_settings
    from app.services.files import page_inbox_dir

    d = page_inbox_dir(get_settings().resolved_files_inbox_path(), page_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(content)


def test_unclaimed_file_listed(admin_client: TestClient) -> None:
    _drop("orphan.png")
    overview = admin_client.get("/api/v1/files").json()
    names = {i["name"]: i for i in overview["inbox"]}
    assert "orphan.png" in names
    assert names["orphan.png"]["status"] == "unclaimed"
    assert overview["counts"]["unclaimed"] >= 1


def test_pending_registration_classified(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="recon-pending")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    _drop("p.png", page_id=page_id)
    r = admin_client.post(
        "/api/v1/internal/register-file",
        json={"inbox_name": "p.png", "display_name": "P", "page_id": page_id},
        headers=internal_headers(agent_id, secret, idempotency_key="rp-1"),
    )
    req_id = r.json()["request_id"]
    overview = admin_client.get("/api/v1/files").json()
    item = next(i for i in overview["inbox"] if i["name"] == "p.png")
    assert item["status"] == "pending_registration"
    assert item["request_id"] == req_id
    assert item["page_id"] == page_id


def test_delete_inbox_file(admin_client: TestClient) -> None:
    _drop("trash.png")
    resp = admin_client.post("/api/v1/files/inbox/delete", json={"name": "trash.png"})
    assert resp.status_code == 204
    overview = admin_client.get("/api/v1/files").json()
    assert all(i["name"] != "trash.png" for i in overview["inbox"])


def test_manual_register_moves_and_lists(admin_client: TestClient) -> None:
    page_id = home_page_id(admin_client)
    _drop("manual.png", page_id=page_id)
    resp = admin_client.post(
        "/api/v1/files/inbox/register",
        json={"name": "manual.png", "display_name": "Manual", "page_id": page_id},
    )
    assert resp.status_code == 200, resp.text
    fid = resp.json()["id"]
    assert resp.json()["agent_id"] is None  # admin-registered, no agent

    overview = admin_client.get("/api/v1/files").json()
    assert any(f["id"] == fid for f in overview["files"])
    # Moved out of the inbox.
    assert all(i["name"] != "manual.png" for i in overview["inbox"])


def test_delete_registered_file_soft_deletes_and_removes_blob(admin_client: TestClient) -> None:
    from app.config import get_settings

    _drop("del.png")
    fid = admin_client.post(
        "/api/v1/files/inbox/register", json={"name": "del.png", "display_name": "D"}
    ).json()["id"]
    blob = get_settings().resolved_files_store_path() / fid / "blob"
    assert blob.is_file()

    assert admin_client.delete(f"/api/v1/files/{fid}").status_code == 204
    assert not blob.exists()
    assert admin_client.get(f"/api/v1/files/{fid}").status_code == 404


def test_store_orphan_detected(admin_client: TestClient) -> None:
    from app.config import get_settings

    store = get_settings().resolved_files_store_path()
    orphan_dir = store / "fil_orphanXYZ"
    orphan_dir.mkdir(parents=True, exist_ok=True)
    (orphan_dir / "blob").write_bytes(b"leftover")
    overview = admin_client.get("/api/v1/files").json()
    ids = {o["file_id"] for o in overview["store_orphans"]}
    assert "fil_orphanXYZ" in ids


def test_orphan_count_counts_unclaimed(admin_client: TestClient) -> None:
    base = admin_client.get("/api/v1/files/orphan-count").json()
    _drop("oc-unclaimed.png")
    after = admin_client.get("/api/v1/files/orphan-count").json()
    assert after["unclaimed"] == base["unclaimed"] + 1
    assert after["total"] == after["unclaimed"] + after["missing"]


def test_orphan_count_counts_missing(admin_client: TestClient) -> None:
    from app.config import get_settings

    _drop("oc-reg.png")
    fid = admin_client.post(
        "/api/v1/files/inbox/register", json={"name": "oc-reg.png", "display_name": "R"}
    ).json()["id"]
    (get_settings().resolved_files_store_path() / fid / "blob").unlink()
    res = admin_client.get("/api/v1/files/orphan-count").json()
    assert res["missing"] >= 1
