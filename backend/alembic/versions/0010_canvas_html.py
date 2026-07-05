"""canvas page kind + html module type

Revision ID: 0010_canvas_html
Revises: 0009_progress
Create Date: 2026-07-04

Adds the agent-controlled HTML page feature:

- Widens the ``modules.type`` CHECK to allow the new ``html`` module type
  (a complete HTML document rendered in a sandboxed iframe — never
  ``allow-same-origin``).
- Widens the ``pages.kind`` CHECK to allow the new ``canvas`` page kind
  (renders its html module full-bleed).
- Seeds a built-in approval rule that makes ``update_module_data`` on html
  modules **prompt** for any owner scope. Its concrete ``module_type`` gives
  it higher specificity than the built-in ``update_module_data/self →
  auto_approve`` rule, so agent HTML rewrites always reach the admin inbox
  by default. Built-ins can be disabled (not deleted) in Settings → Rules
  to opt back into self-owned auto-approve.

CHECK-constraint changes modelled on 0008_corkboard (batch table rebuilds).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from ulid import ULID

from alembic import op

revision: str = "0010_canvas_html"
down_revision: str | Sequence[str] | None = "0009_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


_OLD_MODULE_TYPES = (
    "type IN ('markdown','key_value','table','timeseries','log_stream',"
    "'link_list','iframe','action_button','notification','file','sticky_note','progress')"
)
_NEW_MODULE_TYPES = (
    "type IN ('markdown','key_value','table','timeseries','log_stream',"
    "'link_list','iframe','action_button','notification','file','sticky_note',"
    "'progress','html')"
)

_OLD_PAGE_KINDS = "kind IN ('home','agent','custom','system','corkboard')"
_NEW_PAGE_KINDS = "kind IN ('home','agent','custom','system','corkboard','canvas')"


# NOTE: `pages` is the parent of `modules` (FK ON DELETE CASCADE) and `files`.
# Widening a CHECK forces a full table rebuild (batch ``recreate``), whose internal
# rename/drop would cascade-delete child rows. The alembic env runs migrations with
# FK enforcement OFF for exactly this reason (see alembic/env.py), so child rows
# survive the `pages` rebuild. The running app still enforces FKs.


def upgrade() -> None:
    with op.batch_alter_table("modules", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modules_type", type_="check")
        batch_op.create_check_constraint("ck_modules_type", _NEW_MODULE_TYPES)

    with op.batch_alter_table("pages", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_pages_kind", type_="check")
        batch_op.create_check_constraint("ck_pages_kind", _NEW_PAGE_KINDS)

    now_s = _now()

    rules_table = sa.table(
        "approval_rules",
        sa.column("id", sa.Text),
        sa.column("agent_id", sa.Text),
        sa.column("action_type", sa.Text),
        sa.column("module_type", sa.Text),
        sa.column("module_id", sa.Text),
        sa.column("page_id", sa.Text),
        sa.column("owner_scope", sa.Text),
        sa.column("outcome", sa.Text),
        sa.column("priority", sa.Integer),
        sa.column("is_builtin", sa.Integer),
        sa.column("enabled", sa.Integer),
        sa.column("notes", sa.Text),
        sa.column("created_at", sa.Text),
        sa.column("created_by", sa.Text),
        sa.column("application_count", sa.Integer),
    )
    op.bulk_insert(
        rules_table,
        [
            {
                "id": _new_id("rule"),
                "agent_id": "*",
                "action_type": "update_module_data",
                "module_type": "html",
                "module_id": None,
                "page_id": None,
                "owner_scope": "any",
                "outcome": "prompt",
                "priority": 200,
                "is_builtin": 1,
                "enabled": 1,
                "notes": (
                    "Built-in: html content changes always prompt "
                    "(disable to fall back to self-owned auto-approve)."
                ),
                "created_at": now_s,
                "created_by": "system:bootstrap",
                "application_count": 0,
            }
        ],
    )

    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0010_canvas_html', '{now_s}', NULL)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Remove rows the narrowed CHECKs would reject, then the seeded rule.
    conn.execute(sa.text("DELETE FROM modules WHERE type = 'html'"))
    conn.execute(sa.text("DELETE FROM pages WHERE kind = 'canvas'"))
    conn.execute(
        sa.text(
            "DELETE FROM approval_rules WHERE action_type = 'update_module_data' "
            "AND module_type = 'html' AND is_builtin = 1"
        )
    )

    with op.batch_alter_table("pages", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_pages_kind", type_="check")
        batch_op.create_check_constraint("ck_pages_kind", _OLD_PAGE_KINDS)

    with op.batch_alter_table("modules", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modules_type", type_="check")
        batch_op.create_check_constraint("ck_modules_type", _OLD_MODULE_TYPES)

    op.execute("DELETE FROM schema_migrations WHERE version='0010_canvas_html'")
