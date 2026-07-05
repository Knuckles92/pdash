#!/usr/bin/env python
"""Dev helper: rewrite the default example approval inbox in a live database.

Deletes the existing ``pdash_default_example`` demo agent and its pending
approval requests, then re-inserts the current canonical set from
:mod:`app.seed_approvals` — the same data a fresh install picks up via the
``0004_seed_example_approvals`` migration. Use this after editing the seed
data so a running dev server reflects it *without* resetting the whole database.

    backend/.venv/bin/python backend/scripts/reseed_approvals.py
    backend/.venv/bin/python backend/scripts/reseed_approvals.py --db data/pdash.db
    backend/.venv/bin/python backend/scripts/reseed_approvals.py --dry-run

Direct SQL writes don't emit SSE, so refresh the Approvals page in the browser
to see the new inbox.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.auth.passwords import hash_password  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.ids import new_id  # noqa: E402
from app.modules import validate_config, validate_data  # noqa: E402
from app.seed_approvals import (  # noqa: E402
    EXAMPLE_AGENT_DESCRIPTION,
    EXAMPLE_AGENT_DISPLAY_NAME,
    EXAMPLE_AGENT_KEY_PLAINTEXT,
    EXAMPLE_AGENT_PERMISSIONS,
    IDEMPOTENCY_PREFIX,
    TITLE_CAPACITY_TREND,
    TITLE_SERVICE_HEALTH,
    expires_at,
    home_example_approvals,
)


def _resolve_db_path(override: str | None) -> Path:
    if override:
        return Path(override).resolve()
    path = get_settings().resolved_database_path()
    if path is None:
        raise SystemExit("Could not resolve a SQLite database path; pass --db explicitly.")
    return Path(path).resolve()


def _resolve_home_context(conn: sqlite3.Connection) -> tuple[str | None, dict[str, str]]:
    row = conn.execute(
        "SELECT id FROM pages WHERE slug = 'home' AND deleted_at IS NULL"
    ).fetchone()
    if row is None:
        return None, {}

    home_id = row["id"]
    mod_rows = conn.execute(
        "SELECT id, title FROM modules "
        "WHERE page_id = ? AND deleted_at IS NULL "
        "AND json_extract(permissions, '$.pdash_default_example') = 1",
        (home_id,),
    ).fetchall()
    return home_id, {r["title"]: r["id"] for r in mod_rows}


def _validate_specs(specs: list[dict]) -> None:
    for spec in specs:
        payload = spec["proposed_payload"]
        action = spec["action_type"]
        if action == "create_module":
            validate_data(payload["type"], payload["data"])
            validate_config(payload["type"], payload["config"])
        elif action == "update_module_data":
            patch = payload.get("patch", {})
            if "data" in patch:
                validate_data("key_value", patch["data"])
        elif action == "update_module_config":
            patch = payload.get("patch", {})
            if "config" in patch:
                validate_config("timeseries", patch["config"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reseed the default example pending approval requests."
    )
    parser.add_argument("--db", default=None, help="Path to the SQLite database file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report what would change without writing.",
    )
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args.db)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    now = datetime.now(UTC)
    now_s = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    expires = expires_at(now)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        home_id, modules_by_title = _resolve_home_context(conn)
        if home_id is None:
            raise SystemExit("No 'home' page found in this database.")

        existing_requests = conn.execute(
            "SELECT COUNT(*) AS n FROM approval_requests "
            "WHERE idempotency_key LIKE ?",
            (f"{IDEMPOTENCY_PREFIX}%",),
        ).fetchone()["n"]
        existing_agents = conn.execute(
            "SELECT COUNT(*) AS n FROM agents "
            "WHERE json_extract(permissions, '$.pdash_default_example') = 1"
        ).fetchone()["n"]

        provisional_id = new_id("mod")
        specs = home_example_approvals(
            now,
            home_page_id=home_id,
            modules_by_title=modules_by_title,
            provisional_id=provisional_id,
        )
        _validate_specs(specs)

        print(f"DB:                 {db_path}")
        print(f"Home page:          {home_id}")
        print(f"Example modules:    {len(modules_by_title)} on Home")
        print(f"Existing examples:  {existing_requests} request(s), {existing_agents} agent(s)")
        print(f"New inbox items:    {len(specs)}")
        for spec in specs:
            print(f"  - {spec['action_type']:<22} {spec['idempotency_key']}")
        if TITLE_SERVICE_HEALTH not in modules_by_title:
            print(f"  (skipped update: '{TITLE_SERVICE_HEALTH}' tile not found)")
        if TITLE_CAPACITY_TREND not in modules_by_title:
            print(f"  (skipped update: '{TITLE_CAPACITY_TREND}' tile not found)")

        if args.dry_run:
            print("\n--dry-run: no changes written.")
            return 0

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM approval_requests WHERE idempotency_key LIKE ?",
            (f"{IDEMPOTENCY_PREFIX}%",),
        )
        conn.execute(
            "DELETE FROM agents WHERE json_extract(permissions, '$.pdash_default_example') = 1"
        )

        agent_id = new_id("agt")
        conn.execute(
            "INSERT INTO agents ("
            "id, display_name, description, api_key_hash, permissions, status, "
            "created_at, last_active_at, last_key_rotated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                agent_id,
                EXAMPLE_AGENT_DISPLAY_NAME,
                EXAMPLE_AGENT_DESCRIPTION,
                hash_password(EXAMPLE_AGENT_KEY_PLAINTEXT),
                json.dumps(EXAMPLE_AGENT_PERMISSIONS),
                "active",
                now_s,
                None,
                now_s,
            ),
        )

        for spec in specs:
            conn.execute(
                "INSERT INTO approval_requests ("
                "id, agent_id, action_type, target_kind, target_id, proposed_payload, "
                "idempotency_key, status, created_at, decided_at, decided_by, "
                "decision_reason, applied_at, executed_at, execution_result, expires_at"
                ") VALUES ("
                "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
                ")",
                (
                    new_id("apr"),
                    agent_id,
                    spec["action_type"],
                    spec["target_kind"],
                    spec["target_id"],
                    json.dumps(spec["proposed_payload"]),
                    spec["idempotency_key"],
                    "pending",
                    now_s,
                    None,
                    None,
                    spec["decision_reason"],
                    None,
                    None,
                    None,
                    expires,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"\nReplaced example inbox with {len(specs)} pending request(s). Refresh Approvals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
