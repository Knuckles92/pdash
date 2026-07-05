"""progress module type

Revision ID: 0009_progress
Revises: 0008_corkboard
Create Date: 2026-06-17

Widens the ``modules.type`` CHECK to allow the new ``progress`` module type
(a list of named current/target progress bars), and seeds the ``progress``
example tile onto the Home page.

0001_initial seeds only the module types its own CHECK allows (the original
nine); tiles for types added by later migrations are seeded by those later
migrations. This migration follows that contract: widen the constraint, then
insert the ``progress`` tile from ``home_example_modules()``.

CHECK-constraint change modelled on 0008_corkboard (single-table batch rebuild
of ``modules``).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from ulid import ULID

from alembic import op
from app.seed_home import SEED_VERSION, home_example_modules

revision: str = "0009_progress"
down_revision: str | Sequence[str] | None = "0008_corkboard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


_OLD_MODULE_TYPES = (
    "type IN ('markdown','key_value','table','timeseries','log_stream',"
    "'link_list','iframe','action_button','notification','file','sticky_note')"
)
_NEW_MODULE_TYPES = (
    "type IN ('markdown','key_value','table','timeseries','log_stream',"
    "'link_list','iframe','action_button','notification','file','sticky_note','progress')"
)


def upgrade() -> None:
    with op.batch_alter_table("modules", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modules_type", type_="check")
        batch_op.create_check_constraint("ck_modules_type", _NEW_MODULE_TYPES)

    # Seed the progress example tile onto the Home page.
    now_s = _now()
    now_dt = datetime.now(UTC)
    progress_spec = next(
        (s for s in home_example_modules(now_dt) if s["type"] == "progress"), None
    )
    if progress_spec is not None:
        conn = op.get_bind()
        home_row = conn.execute(
            sa.text("SELECT id FROM pages WHERE slug = 'home' AND deleted_at IS NULL")
        ).fetchone()
        if home_row is not None:
            home_id = home_row[0]
            max_pos_row = conn.execute(
                sa.text(
                    "SELECT COALESCE(MAX(position), -1) "
                    "FROM modules WHERE page_id = :pid AND deleted_at IS NULL"
                ),
                {"pid": home_id},
            ).fetchone()
            next_pos = (max_pos_row[0] if max_pos_row else -1) + 1

            modules_table = sa.table(
                "modules",
                sa.column("id", sa.Text),
                sa.column("type", sa.Text),
                sa.column("title", sa.Text),
                sa.column("owner_kind", sa.Text),
                sa.column("owner_id", sa.Text),
                sa.column("page_id", sa.Text),
                sa.column("position", sa.Integer),
                sa.column("grid", sa.Text),
                sa.column("permissions", sa.Text),
                sa.column("data", sa.Text),
                sa.column("config", sa.Text),
                sa.column("schema_version", sa.Integer),
                sa.column("version", sa.Integer),
                sa.column("created_at", sa.Text),
                sa.column("updated_at", sa.Text),
                sa.column("last_updated_by", sa.Text),
            )
            op.bulk_insert(
                modules_table,
                [
                    {
                        "id": _new_id("mod"),
                        "type": progress_spec["type"],
                        "title": progress_spec["title"],
                        "owner_kind": "user",
                        "owner_id": "admin",
                        "page_id": home_id,
                        "position": next_pos,
                        "grid": json.dumps({"colspan": progress_spec.get("colspan", 1)}),
                        "permissions": json.dumps(
                            {"pdash_default_example": True, "seed_version": SEED_VERSION}
                        ),
                        "data": json.dumps(progress_spec["data"]),
                        "config": json.dumps(progress_spec["config"]),
                        "schema_version": 1,
                        "version": 1,
                        "created_at": now_s,
                        "updated_at": now_s,
                        "last_updated_by": "system:bootstrap",
                    }
                ],
            )

    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0009_progress', '{now_s}', NULL)"
    )


def downgrade() -> None:
    # Remove the progress seed tile so the constraint can narrow again.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM modules WHERE type = 'progress' "
            "AND json_extract(permissions, '$.pdash_default_example') = 1"
        )
    )

    with op.batch_alter_table("modules", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modules_type", type_="check")
        batch_op.create_check_constraint("ck_modules_type", _OLD_MODULE_TYPES)

    op.execute("DELETE FROM schema_migrations WHERE version='0009_progress'")
