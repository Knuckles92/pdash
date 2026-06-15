"""agent_registration_requests table (agent-first MCP onboarding)

Revision ID: 0006_agent_registrations
Revises: 0005_files
Create Date: 2026-06-14

Adds the persistence for agent self-registration. A keyless AI client connects
to the MCP server and requests registration via the ungated bootstrap surface
(see ``api/internal_bootstrap.py``); the request lands here as ``pending`` for
the admin to approve in Settings -> Agents. No agent key is minted until the
admin approves AND the client claims it (mint-on-claim) — so this table holds
no agent key, only a sha256 of a one-time claim token the client polls with.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0006_agent_registrations"
down_revision: str | Sequence[str] | None = "0005_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def upgrade() -> None:
    op.create_table(
        "agent_registration_requests",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("requested_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("client_hint", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("claim_token_hash", sa.Text(), nullable=False),
        sa.Column("permissions", sa.Text(), nullable=True),
        sa.Column(
            "agent_id",
            sa.Text(),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','approved','denied','claimed','expired')",
            name="ck_areg_status",
        ),
        sa.CheckConstraint(
            "permissions IS NULL OR json_valid(permissions)",
            name="ck_areg_perm_json",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_areg_claim_token "
        "ON agent_registration_requests(claim_token_hash)"
    )
    op.execute(
        "CREATE INDEX idx_areg_status_created "
        "ON agent_registration_requests(status, created_at DESC)"
    )

    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0006_agent_registrations', '{_now()}', NULL)"
    )


def downgrade() -> None:
    op.drop_table("agent_registration_requests")
    op.execute("DELETE FROM schema_migrations WHERE version='0006_agent_registrations'")
