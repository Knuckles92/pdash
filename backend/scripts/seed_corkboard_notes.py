"""Seed a handful of sample sticky notes onto the corkboard page.

One-shot sample data for the demo corkboard — not part of the canonical Home
seed (``seed_home``). Idempotent: any note whose text already exists on the
page is skipped, so this is safe to re-run.

Run from the backend dir:
    .venv/bin/python -m scripts.seed_corkboard_notes
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from app.config import get_settings
from app.ids import new_id
from app.modules import validate_config, validate_data
from app.timefmt import utcnow_iso


def _db_path() -> Path:
    """PDASH_DATABASE_PATH if set, else the default dev location (repo data/)."""
    resolved = get_settings().resolved_database_path()
    if resolved:
        return resolved
    return Path(__file__).resolve().parents[2] / "data" / "pdash.db"

# Each note: (data, config). `data` carries title / markdown body / checklist /
# pinned; ordering is by recency (pinned first) — no free-form positions anymore.
SAMPLES: list[tuple[dict, dict]] = [
    (
        {
            "title": "Today's focus",
            "items": [
                {"text": "Ship the notes redesign", "done": False},
                {"text": "Review agent approvals", "done": False},
                {"text": "Backups verified", "done": True},
            ],
            "pinned": True,
        },
        {"color": "yellow"},
    ),
    (
        {
            "title": "Don't forget",
            "text": "- Renew Tailscale cert (expires soon)\n"
            "- Reply to Jamie\n"
            "- Water the plants 🌱",
        },
        {"color": "pink"},
    ),
    (
        {
            "title": "Ideas 💡",
            "text": "- Auto-summary of overnight activity\n"
            "- Per-page agent permissions\n"
            "- Calendar widget module",
        },
        {"color": "blue"},
    ),
    (
        {
            "title": "Shopping",
            "items": [
                {"text": "Coffee beans", "done": True},
                {"text": "SSD (2TB)", "done": True},
                {"text": "USB-C cables", "done": False},
                {"text": "Cable ties", "done": False},
            ],
        },
        {"color": "green"},
    ),
    (
        {
            "title": "Homelab",
            "text": "`proxmox` — 4 nodes · 18TB usable\n\n"
            "power **142W** avg · uptime 41 days ⚡",
        },
        {"color": "orange"},
    ),
    (
        {"text": "_Simplicity is the soul of efficiency._\n\n— Austin Freeman"},
        {"color": "purple"},
    ),
    (
        {
            "title": "Key contacts",
            "text": "ISP support · ext 3\n"
            "Electrician · 555-0142\n"
            "Tailscale ACL: review monthly",
        },
        {"color": "white"},
    ),
]


def main() -> int:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row

    page = con.execute(
        "SELECT id FROM pages WHERE type='corkboard' AND deleted_at IS NULL",
    ).fetchone()
    if page is None:
        print("No corkboard page found.", file=sys.stderr)
        return 1
    page_id = page["id"]

    existing = {
        (json.loads(r["data"]).get("title", ""), json.loads(r["data"]).get("text", ""))
        for r in con.execute(
            "SELECT data FROM modules "
            "WHERE type='sticky_note' AND page_id=? AND deleted_at IS NULL",
            (page_id,),
        )
    }

    now = utcnow_iso()
    inserted = 0
    rows = []
    for data, config in SAMPLES:
        key = (data.get("title", ""), data.get("text", ""))
        if key in existing:
            continue
        # Validate against the sticky_note Pydantic models (fills defaults,
        # guards the on-read render-health check).
        data_json = json.dumps(validate_data("sticky_note", data))
        config_json = json.dumps(validate_config("sticky_note", config))
        rows.append(
            (
                new_id("mod"),
                "sticky_note",
                "user",        # owner_kind (admin direct write, like the UI)
                "admin",       # owner_id
                page_id,
                0,             # position (board orders by pinned-then-recency)
                "{}",          # permissions
                data_json,
                config_json,
                None,          # grid (no free-form board position anymore)
                1,             # schema_version
                now,           # created_at
                now,           # updated_at
                "user:admin",  # last_updated_by
            )
        )
        inserted += 1

    if inserted:
        con.executemany(
            "INSERT INTO modules (id, type, owner_kind, owner_id, page_id, position, "
            "permissions, data, config, grid, schema_version, created_at, updated_at, "
            "last_updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        con.commit()
        print(f"Inserted {inserted} sample notes onto corkboard page {page_id}.")
    else:
        print("All sample notes already present — nothing to insert.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
