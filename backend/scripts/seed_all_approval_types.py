#!/usr/bin/env python
"""Enqueue one pending approval per action_type for Approvals inbox UI testing.

Hits the live dev server (default http://127.0.0.1:8080). Safe to re-run — each
invocation uses a unique timestamp prefix.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.approval.expiry import compute_expires_at
from app.config import get_settings
from app.ids import new_id
from app.services.files import page_inbox_dir
from app.timefmt import iso_millis
from datetime import UTC, datetime

BASE = "http://127.0.0.1:8080"
PREFIX = f"demo-{int(time.time())}"


def _load_secret() -> str:
    env_path = _BACKEND.parent / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("PDASH_SERVICE_SECRET="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("PDASH_SERVICE_SECRET not found in .env")


def _request(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw.decode()}
        return exc.code, payload


def _insert_delete_page_approval(agent_id: str, page_id: str) -> str:
    """delete_page has no internal agent route yet — insert a pending row directly."""
    import sqlite3

    db = get_settings().resolved_database_path()
    if db is None:
        raise SystemExit("Could not resolve database path")
    apr_id = new_id("apr")
    now = iso_millis(datetime.now(UTC))
    payload = json.dumps({"id": page_id, "cascade": False}, separators=(",", ":"))
    conn = sqlite3.connect(str(db), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(
        "INSERT INTO approval_requests "
        "(id, agent_id, action_type, target_kind, target_id, proposed_payload, "
        "status, created_at, expires_at, decision_reason) "
        "VALUES (?, ?, 'delete_page', 'page', ?, ?, 'pending', ?, ?, ?)",
        (
            apr_id,
            agent_id,
            page_id,
            payload,
            now,
            compute_expires_at(),
            "UI test — delete_page",
        ),
    )
    conn.commit()
    conn.close()
    return apr_id


def main() -> int:
    secret = _load_secret()

    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login_req = urllib.request.Request(
        f"{BASE}/api/v1/auth/login",
        data=json.dumps({"password": "dev"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener.open(login_req, timeout=30)
    except urllib.error.HTTPError as exc:
        print(f"login failed: {exc.code} {exc.read().decode()}")
        return 1
    cookies = {c.name: c.value for c in jar}
    csrf = cookies.get("csrf_token", "")

    def admin(method: str, path: str, body: dict | None = None) -> dict:
        hdrs = {"X-CSRF-Token": csrf}
        status, payload = _request(method, path, body=body, headers=hdrs, cookies=cookies)
        if status >= 400:
            raise SystemExit(f"{method} {path} failed ({status}): {payload}")
        return payload

    agent = admin("POST", "/api/v1/agents", {"display_name": f"inbox-seed-{PREFIX}"})
    agent_id = agent["agent"]["id"]

    def internal(path: str, body: dict, key: str) -> tuple[str, int, dict]:
        hdrs = {
            "Authorization": f"Bearer {secret}",
            "X-Agent-Id": agent_id,
            "Idempotency-Key": f"{PREFIX}-{key}",
            "X-CSRF-Token": csrf,
        }
        status, payload = _request("POST", path, body=body, headers=hdrs, cookies=cookies)
        req_id = payload.get("request_id") or payload.get("id")
        return key, status, payload

    pages = _request("GET", "/api/v1/pages?limit=50", headers={"X-CSRF-Token": csrf}, cookies=cookies)
    if pages[0] != 200:
        raise SystemExit(f"list pages failed: {pages}")
    home_id = next(p["id"] for p in pages[1]["items"] if p["slug"] == "home")

    created: list[tuple[str, str | None, int]] = []

    _, status, payload = internal(
        "/api/v1/internal/propose-module",
        {
            "type": "markdown",
            "page_id": home_id,
            "title": "Demo: create module",
            "position": 90,
            "data": {"body": "Pending create_module proposal for inbox UI testing."},
            "config": {},
            "rationale": "UI test — create_module",
        },
        "create-module",
    )
    created.append(("create_module", payload.get("request_id"), status))

    def admin_module(title: str, position: int) -> str:
        mod = admin(
            "POST",
            "/api/v1/modules",
            {
                "type": "markdown",
                "page_id": home_id,
                "title": title,
                "position": position,
                "owner_kind": "agent",
                "owner_id": agent_id,
                "data": {"body": "Fixture module for approval demos."},
                "config": {
                    "collapsed_by_default": False,
                    "max_height_px": 400,
                    "show_rendered_at": False,
                },
            },
        )
        return mod["id"]

    mod_data = admin_module(f"Demo data target ({PREFIX})", 91)
    mod_cfg = admin_module(f"Demo config target ({PREFIX})", 92)
    mod_meta = admin_module(f"Demo meta target ({PREFIX})", 93)
    mod_del = admin_module(f"Demo delete target ({PREFIX})", 94)

    _, status, payload = internal(
        "/api/v1/internal/update-module",
        {
            "id": mod_data,
            "patch": {"data": {"body": "Proposed new body text for data update preview."}},
            "rationale": "UI test — update_module_data",
        },
        "update-data",
    )
    created.append(("update_module_data", payload.get("request_id"), status))

    _, status, payload = internal(
        "/api/v1/internal/update-module",
        {
            "id": mod_cfg,
            "patch": {"config": {"max_height_px": 520, "collapsed_by_default": True}},
            "rationale": "UI test — update_module_config",
        },
        "update-config",
    )
    created.append(("update_module_config", payload.get("request_id"), status))

    _, status, payload = internal(
        "/api/v1/internal/update-module",
        {
            "id": mod_meta,
            "patch": {"title": f"Renamed tile ({PREFIX})"},
            "rationale": "UI test — update_module_meta",
        },
        "update-meta",
    )
    created.append(("update_module_meta", payload.get("request_id"), status))

    _, status, payload = internal(
        "/api/v1/internal/delete-module",
        {"id": mod_del, "rationale": "UI test — delete_module"},
        "delete-module",
    )
    created.append(("delete_module", payload.get("request_id"), status))

    _, status, payload = internal(
        "/api/v1/internal/propose-page",
        {
            "name": f"Demo page {PREFIX}",
            "slug": f"demo-page-{PREFIX}",
            "description": "Pending create_page proposal",
            "rationale": "UI test — create_page",
        },
        "create-page",
    )
    created.append(("create_page", payload.get("request_id"), status))

    del_page = admin(
        "POST",
        "/api/v1/pages",
        {
            "name": f"Delete me {PREFIX}",
            "slug": f"del-page-{PREFIX}",
            "description": "Fixture for delete_page approval",
            "type": "custom",
        },
    )
    apr_del_page = _insert_delete_page_approval(agent_id, del_page["id"])
    created.append(("delete_page", apr_del_page, 201))

    target = admin(
        "POST",
        "/api/v1/action-targets",
        {
            "name": f"demo-hook-{PREFIX}",
            "kind": "webhook",
            "mode": "sync",
            "config": {"url": "https://hooks.example.local/demo", "method": "post"},
        },
    )
    _, status, payload = internal(
        "/api/v1/internal/fire-action",
        {"target_id": target["id"], "payload": {"event": "demo", "source": PREFIX}},
        "fire-action",
    )
    created.append(("fire_action_button", payload.get("request_id"), status))

    inbox = page_inbox_dir(get_settings().resolved_files_inbox_path(), home_id)
    inbox.mkdir(parents=True, exist_ok=True)
    inbox_name = f"demo-{PREFIX}.txt"
    (inbox / inbox_name).write_text("Sample file for register_file approval preview.\n")

    _, status, payload = internal(
        "/api/v1/internal/register-file",
        {
            "inbox_name": inbox_name,
            "display_name": f"Demo file ({PREFIX})",
            "page_id": home_id,
            "purpose": "Approvals inbox UI test",
        },
        "register-file",
    )
    created.append(("register_file", payload.get("request_id"), status))

    status, payload = _request(
        "POST",
        "/api/v1/internal/bootstrap/register",
        body={
            "display_name": f"reg-demo-{PREFIX}",
            "description": "Pending register_agent proposal",
            "rationale": "UI test — register_agent",
            "client_hint": "seed_all_approval_types.py",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )
    reg_id = payload.get("registration_id")
  # register also creates approval_request - fetch it
    listing_status, listing = _request(
        "GET",
        f"/api/v1/approval-requests?status=pending&action_type=register_agent&limit=20",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
    )
    apr_reg = None
    if listing_status == 200:
        for item in listing.get("items", []):
            if item.get("target_id") == reg_id:
                apr_reg = item["id"]
                break
    created.append(("register_agent", apr_reg, status))

    print(f"Seeded pending approvals (prefix={PREFIX}):")
    for action_type, req_id, status in created:
        mark = "ok" if status in (200, 201, 202) else "FAIL"
        print(f"  [{mark}] {action_type:<22} {req_id or '—'} (http {status})")
    print("\nRefresh http://localhost:3000/approvals to see them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
