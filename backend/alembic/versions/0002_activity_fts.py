"""FTS5 virtual table for activity_log search.

Revision ID: 0002_activity_fts
Revises: 0001_initial
Create Date: 2026-05-25

Creates ``activity_log_fts`` as an external-content FTS5 table mirroring
``activity_log.payload_summary``, ``outcome``, and ``action_type``. Triggers
keep it in sync; an initial backfill populates the index with existing rows.

Querying::

    SELECT a.* FROM activity_log a
    JOIN activity_log_fts f ON f.rowid = a.id
    WHERE activity_log_fts MATCH ?
    ORDER BY bm25(activity_log_fts);
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op

revision: str = "0002_activity_fts"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def upgrade() -> None:
    # External-content FTS5 table tied to activity_log.
    # `tokenize='unicode61'` is the SQLite default; explicit for clarity.
    op.execute(
        """
        CREATE VIRTUAL TABLE activity_log_fts USING fts5(
            payload_summary,
            outcome,
            action_type,
            content='activity_log',
            content_rowid='id',
            tokenize='unicode61'
        )
        """
    )

    # Backfill existing rows.
    op.execute(
        """
        INSERT INTO activity_log_fts(rowid, payload_summary, outcome, action_type)
        SELECT id, COALESCE(payload_summary, ''), outcome, action_type
        FROM activity_log
        """
    )

    # Keep-in-sync triggers. We use the standard "external content" pattern:
    # delete/insert to keep the FTS index in lockstep.
    op.execute(
        """
        CREATE TRIGGER activity_log_ai AFTER INSERT ON activity_log BEGIN
            INSERT INTO activity_log_fts(rowid, payload_summary, outcome, action_type)
            VALUES (new.id, COALESCE(new.payload_summary, ''), new.outcome, new.action_type);
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER activity_log_ad AFTER DELETE ON activity_log BEGIN
            INSERT INTO activity_log_fts(activity_log_fts, rowid, payload_summary, outcome, action_type)
            VALUES('delete', old.id, COALESCE(old.payload_summary, ''), old.outcome, old.action_type);
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER activity_log_au AFTER UPDATE ON activity_log BEGIN
            INSERT INTO activity_log_fts(activity_log_fts, rowid, payload_summary, outcome, action_type)
            VALUES('delete', old.id, COALESCE(old.payload_summary, ''), old.outcome, old.action_type);
            INSERT INTO activity_log_fts(rowid, payload_summary, outcome, action_type)
            VALUES (new.id, COALESCE(new.payload_summary, ''), new.outcome, new.action_type);
        END;
        """
    )

    # Record this migration in schema_migrations.
    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0002_activity_fts', '{_now()}', NULL)"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS activity_log_au")
    op.execute("DROP TRIGGER IF EXISTS activity_log_ad")
    op.execute("DROP TRIGGER IF EXISTS activity_log_ai")
    op.execute("DROP TABLE IF EXISTS activity_log_fts")
    op.execute("DELETE FROM schema_migrations WHERE version='0002_activity_fts'")
