"""Persistent rate-limit buckets per agent + action class.

Revision ID: 0003_rate_limits
Revises: 0002_activity_fts
Create Date: 2026-05-25

One row per (agent_id, action_class); ``action_class`` is ``read`` or
``write`` in v1. Persisted so the bucket survives restarts.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0003_rate_limits"
down_revision: str | Sequence[str] | None = "0002_activity_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def upgrade() -> None:
    op.create_table(
        "agent_rate_limits",
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("action_class", sa.Text(), nullable=False),
        sa.Column("tokens", sa.Float(), nullable=False),
        sa.Column("last_refill", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("agent_id", "action_class", name="pk_agent_rate_limits"),
        sa.CheckConstraint(
            "action_class IN ('read','write')", name="ck_arl_action_class",
        ),
    )
    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0003_rate_limits', '{_now()}', NULL)"
    )


def downgrade() -> None:
    op.drop_table("agent_rate_limits")
    op.execute("DELETE FROM schema_migrations WHERE version='0003_rate_limits'")
