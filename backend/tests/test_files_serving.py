"""Tests for serving registered files (``/api/v1/files/{id}/raw|/download``).

The security contract: only a tiny MIME allowlist is served inline; risky types
(html/svg/js) are forced to ``application/octet-stream`` + attachment, always
with ``X-Content-Type-Options: nosniff``. Serving is admin-session only.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _admin_register(
    admin_client: TestClient,
    name: str,
    *,
    content: bytes = b"bytes",
    display_name: str = "F",
) -> str:
    from app.config import get_settings

    inbox = get_settings().resolved_files_inbox_path()
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / name).write_bytes(content)
    resp = admin_client.post(
        "/api/v1/files/inbox/register",
        json={"name": name, "display_name": display_name},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_image_served_inline_with_nosniff(admin_client: TestClient) -> None:
    fid = _admin_register(admin_client, "pic.png", content=b"\x89PNG\r\n\x1a\nx")
    resp = admin_client.get(f"/api/v1/files/{fid}/raw")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.content == b"\x89PNG\r\n\x1a\nx"


def test_html_forced_to_attachment(admin_client: TestClient) -> None:
    fid = _admin_register(admin_client, "evil.html", content=b"<script>alert(1)</script>")
    resp = admin_client.get(f"/api/v1/files/{fid}/raw")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_svg_forced_to_attachment(admin_client: TestClient) -> None:
    # SVG is kind=image but NOT inline-safe (can carry script) -> attachment.
    fid = _admin_register(admin_client, "logo.svg", content=b"<svg onload=alert(1)>")
    resp = admin_client.get(f"/api/v1/files/{fid}/raw")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert resp.headers["content-disposition"].startswith("attachment")


def test_download_always_attachment(admin_client: TestClient) -> None:
    fid = _admin_register(admin_client, "pic.png", content=b"\x89PNGx")
    resp = admin_client.get(f"/api/v1/files/{fid}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert resp.headers["content-disposition"].startswith("attachment")


def test_unauthenticated_serve_rejected(admin_client: TestClient) -> None:
    fid = _admin_register(admin_client, "pic.png")
    from app.main import create_app

    fresh = TestClient(create_app())  # logged-out client, same DB
    resp = fresh.get(f"/api/v1/files/{fid}/raw")
    assert resp.status_code in (401, 403)


def test_unknown_id_404(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/files/fil_does_not_exist/raw")
    assert resp.status_code == 404


def test_deleted_file_404(admin_client: TestClient) -> None:
    fid = _admin_register(admin_client, "gone.png")
    assert admin_client.delete(f"/api/v1/files/{fid}").status_code == 204
    assert admin_client.get(f"/api/v1/files/{fid}/raw").status_code == 404


def test_missing_on_disk_404(admin_client: TestClient) -> None:
    from app.config import get_settings

    fid = _admin_register(admin_client, "vanish.png")
    # Remove the blob behind the row's back (stored at <store>/<fid>/blob).
    blob = get_settings().resolved_files_store_path() / fid / "blob"
    blob.unlink()
    assert admin_client.get(f"/api/v1/files/{fid}/raw").status_code == 404
