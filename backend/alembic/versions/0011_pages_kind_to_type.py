"""rename pages.kind → pages.type

Revision ID: 0011_pages_kind_to_type
Revises: 0010_canvas_html
Create Date: 2026-07-09

Renames the page discriminator column from ``kind`` to ``type`` so it
parallels ``modules.type``. Values are unchanged
(``home|agent|custom|system|corkboard|canvas``).

CHECK-constraint + column rename via batch table rebuild (same FK-off
pattern as 0008/0010 — see alembic/env.py).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op

revision: str = "0011_pages_kind_to_type"
down_revision: str | Sequence[str] | None = "0010_canvas_html"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PAGE_TYPES = "type IN ('home','agent','custom','system','corkboard','canvas')"
_PAGE_KINDS = "kind IN ('home','agent','custom','system','corkboard','canvas')"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# NOTE: `pages` is the parent of `modules` (FK ON DELETE CASCADE) and `files`.
# Renaming a column + swapping a CHECK forces a full table rebuild (batch
# ``recreate``), whose internal rename/drop would cascade-delete child rows.
# The alembic env runs migrations with FK enforcement OFF for exactly this
# reason (see alembic/env.py), so child rows survive. The running app still
# enforces FKs.


def upgrade() -> None:
    with op.batch_alter_table("pages", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_pages_kind", type_="check")
        batch_op.alter_column("kind", new_column_name="type")
        batch_op.create_check_constraint("ck_pages_type", _PAGE_TYPES)

    now_s = _now()
    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0011_pages_kind_to_type', '{now_s}', NULL)"
    )


def downgrade() -> None:
    with op.batch_alter_table("pages", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_pages_type", type_="check")
        batch_op.alter_column("type", new_column_name="kind")
        batch_op.create_check_constraint("ck_pages_kind", _PAGE_KINDS)

    op.execute("DELETE FROM schema_migrations WHERE version='0011_pages_kind_to_type'")
