"""corkboard page kind + sticky_note module type

Revision ID: 0008_corkboard
Revises: 0007_register_agent_approvals
Create Date: 2026-06-17

Adds the corkboard board feature:

- Widens the ``modules.type`` CHECK to allow the new ``sticky_note`` module type
  (a single pinned note; board position lives in the existing ``grid`` JSON blob).
- Widens the ``pages.kind`` CHECK to allow the new ``corkboard`` page kind.

Both are CHECK-constraint changes, which SQLite can only do via a batch table
rebuild (modelled on 0005_files). ``pages`` is referenced by ``modules.page_id``
and ``files.page_id``; Alembic's batch ``recreate`` keeps those child references
intact (it sets ``PRAGMA legacy_alter_table`` during the swap), so no child rows
are cascaded/nulled.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op

revision: str = "0008_corkboard"
down_revision: str | Sequence[str] | None = "0007_register_agent_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


_OLD_MODULE_TYPES = (
    "type IN ('markdown','key_value','table','timeseries','log_stream',"
    "'link_list','iframe','action_button','notification','file')"
)
_NEW_MODULE_TYPES = (
    "type IN ('markdown','key_value','table','timeseries','log_stream',"
    "'link_list','iframe','action_button','notification','file','sticky_note')"
)

_OLD_PAGE_KINDS = "kind IN ('home','agent','custom','system')"
_NEW_PAGE_KINDS = "kind IN ('home','agent','custom','system','corkboard')"


# NOTE: `pages` is the parent of `modules` (FK ON DELETE CASCADE) and `files`.
# Widening a CHECK forces a full table rebuild (batch ``recreate``), whose internal
# rename/drop would cascade-delete child rows. The alembic env runs migrations with
# FK enforcement OFF for exactly this reason (see alembic/env.py), so the seeded home
# example modules survive the `pages` rebuild. The running app still enforces FKs.


def upgrade() -> None:
    with op.batch_alter_table("modules", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modules_type", type_="check")
        batch_op.create_check_constraint("ck_modules_type", _NEW_MODULE_TYPES)

    with op.batch_alter_table("pages", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_pages_kind", type_="check")
        batch_op.create_check_constraint("ck_pages_kind", _NEW_PAGE_KINDS)

    now_s = _now()
    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0008_corkboard', '{now_s}', NULL)"
    )


def downgrade() -> None:
    with op.batch_alter_table("pages", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_pages_kind", type_="check")
        batch_op.create_check_constraint("ck_pages_kind", _OLD_PAGE_KINDS)

    with op.batch_alter_table("modules", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modules_type", type_="check")
        batch_op.create_check_constraint("ck_modules_type", _OLD_MODULE_TYPES)

    op.execute("DELETE FROM schema_migrations WHERE version='0008_corkboard'")
