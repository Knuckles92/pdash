"""files table + file module type + register_file built-in rule

Revision ID: 0005_files
Revises: 0004_seed_example_approvals
Create Date: 2026-05-31

Adds the agent file-drop feature's persistence:

- Widens the ``modules.type`` CHECK to allow the new ``file`` module type.
- Creates the ``files`` table (one row per registered file).
- Seeds the built-in ``register_file -> prompt`` approval rule (parity with the
  nine rules seeded in 0001; the engine already defaults to ``prompt`` when no
  rule matches, but the explicit built-in is discoverable/retargetable in the
  rules UI).
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from ulid import ULID

from alembic import op

revision: str = "0005_files"
down_revision: str | Sequence[str] | None = "0004_seed_example_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


_OLD_MODULE_TYPES = (
    "type IN ('markdown','key_value','table','timeseries','log_stream',"
    "'link_list','iframe','action_button','notification')"
)
_NEW_MODULE_TYPES = (
    "type IN ('markdown','key_value','table','timeseries','log_stream',"
    "'link_list','iframe','action_button','notification','file')"
)


def upgrade() -> None:
    now_s = _now()

    # ------------------------------------------------------------------
    # Widen modules.type CHECK to include the new 'file' module type.
    # `modules` has no incoming FK references, so the batch table rebuild is
    # safe (no child rows get nulled during the swap).
    # ------------------------------------------------------------------
    with op.batch_alter_table("modules", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modules_type", type_="check")
        batch_op.create_check_constraint("ck_modules_type", _NEW_MODULE_TYPES)

    # ------------------------------------------------------------------
    # files
    # ------------------------------------------------------------------
    op.create_table(
        "files",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.Text(),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("inbox_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="registered"),
        sa.Column(
            "page_id",
            sa.Text(),
            sa.ForeignKey("pages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('registered','deleted')", name="ck_files_status"),
        sa.CheckConstraint("kind IN ('image','document')", name="ck_files_kind"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_files_size"),
    )
    op.execute("CREATE INDEX idx_files_agent ON files(agent_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX idx_files_page ON files(page_id)")
    op.execute("CREATE INDEX idx_files_sha ON files(sha256)")

    # ------------------------------------------------------------------
    # Seed: built-in register_file -> prompt rule (parity with 0001).
    # ------------------------------------------------------------------
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
                "action_type": "register_file",
                "module_type": None,
                "module_id": None,
                "page_id": None,
                "owner_scope": "any",
                "outcome": "prompt",
                "priority": 200,
                "is_builtin": 1,
                "enabled": 1,
                "notes": "Built-in default rule for register_file/any.",
                "created_at": now_s,
                "created_by": "system:bootstrap",
                "application_count": 0,
            }
        ],
    )

    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0005_files', '{now_s}', NULL)"
    )


def downgrade() -> None:
    op.execute("DELETE FROM approval_rules WHERE action_type='register_file' AND is_builtin=1")
    op.drop_table("files")
    with op.batch_alter_table("modules", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modules_type", type_="check")
        batch_op.create_check_constraint("ck_modules_type", _OLD_MODULE_TYPES)
    op.execute("DELETE FROM schema_migrations WHERE version='0005_files'")
