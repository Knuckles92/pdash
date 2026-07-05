#!/usr/bin/env python
"""Dev helper: rewrite the default "Home" example tiles in a live database.

Deletes the existing ``pdash_default_example`` modules on the home page and
re-inserts the current canonical layout from :mod:`app.seed_home` — the same
data a fresh install is seeded with. Use this after editing the layout so a
running dev server reflects it *without* resetting the whole database; your
admin session, secrets, and any other pages/modules are left untouched.

    backend/.venv/bin/python backend/scripts/reseed_home.py            # default DB
    backend/.venv/bin/python backend/scripts/reseed_home.py --db data/pdash.db
    backend/.venv/bin/python backend/scripts/reseed_home.py --dry-run

Direct SQL writes don't emit SSE, so refresh the dashboard in the browser to
see the new layout.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# Make the backend package importable when run by file path from the repo root.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.ids import new_id  # noqa: E402
from app.modules import validate_config, validate_data  # noqa: E402
from app.seed_home import SEED_VERSION, home_example_modules  # noqa: E402


def _resolve_db_path(override: str | None) -> Path:
    if override:
        return Path(override).resolve()
    path = get_settings().resolved_database_path()
    if path is None:
        raise SystemExit("Could not resolve a SQLite database path; pass --db explicitly.")
    return Path(path).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reseed the default Home example tiles.")
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
    permissions = json.dumps({"pdash_default_example": True, "seed_version": SEED_VERSION})

    # Validate every tile against the real module schemas before touching the DB.
    specs = home_example_modules(now)
    for spec in specs:
        validate_data(spec["type"], spec["data"])
        validate_config(spec["type"], spec["config"])

    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id FROM pages WHERE slug = 'home' AND deleted_at IS NULL"
        ).fetchone()
        if row is None:
            raise SystemExit("No 'home' page found in this database.")
        home_id = row["id"]

        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM modules "
            "WHERE page_id = ? "
            "AND json_extract(permissions, '$.pdash_default_example') = 1",
            (home_id,),
        ).fetchone()["n"]

        print(f"DB:        {db_path}")
        print(f"Home page: {home_id}")
        print(f"Existing default-example tiles: {existing}")
        print(f"New layout tiles:               {len(specs)}")
        for i, spec in enumerate(specs):
            print(f"  [{i}] {spec['type']:<14} colspan={spec.get('colspan', 1)}  {spec['title']}")

        if args.dry_run:
            print("\n--dry-run: no changes written.")
            return 0

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM modules "
            "WHERE page_id = ? "
            "AND json_extract(permissions, '$.pdash_default_example') = 1",
            (home_id,),
        )
        conn.executemany(
            "INSERT INTO modules ("
            "id, type, title, owner_kind, owner_id, page_id, position, grid, "
            "permissions, data, config, schema_version, version, created_at, "
            "updated_at, last_updated_by"
            ") VALUES ("
            ":id, :type, :title, :owner_kind, :owner_id, :page_id, :position, :grid, "
            ":permissions, :data, :config, :schema_version, :version, :created_at, "
            ":updated_at, :last_updated_by"
            ")",
            [
                {
                    "id": new_id("mod"),
                    "type": spec["type"],
                    "title": spec["title"],
                    "owner_kind": "user",
                    "owner_id": "admin",
                    "page_id": home_id,
                    "position": i,
                    "grid": json.dumps({"colspan": spec.get("colspan", 1)}),
                    "permissions": permissions,
                    "data": json.dumps(spec["data"]),
                    "config": json.dumps(spec["config"]),
                    "schema_version": 1,
                    "version": 1,
                    "created_at": now_s,
                    "updated_at": now_s,
                    "last_updated_by": "system:reseed",
                }
                for i, spec in enumerate(specs)
            ],
        )
        conn.commit()
    finally:
        conn.close()

    print(f"\nReplaced {existing} tile(s) with {len(specs)}. Refresh the dashboard to see it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
