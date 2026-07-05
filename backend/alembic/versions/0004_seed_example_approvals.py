"""Seed example pending approval requests for the admin inbox.

Revision ID: 0004_seed_example_approvals
Revises: 0003_rate_limits
Create Date: 2026-05-29

Inserts a demo agent (Home Bot) and up to three pending approval requests
targeting the default Home example tiles. Idempotent on re-run: deletes prior
rows tagged with ``pdash_default_example`` markers before inserting fresh ones.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from ulid import ULID

from alembic import op
from app.auth.passwords import hash_password
from app.seed_approvals import (
    EXAMPLE_AGENT_DESCRIPTION,
    EXAMPLE_AGENT_DISPLAY_NAME,
    EXAMPLE_AGENT_KEY_PLAINTEXT,
    EXAMPLE_AGENT_PERMISSIONS,
    IDEMPOTENCY_PREFIX,
    expires_at,
    home_example_approvals,
)

revision: str = "0004_seed_example_approvals"
down_revision: str | Sequence[str] | None = "0003_rate_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _resolve_home_context(bind) -> tuple[str | None, dict[str, str]]:
    home_row = bind.execute(
        sa.text("SELECT id FROM pages WHERE slug = 'home' AND deleted_at IS NULL")
    ).fetchone()
    if home_row is None:
        return None, {}

    home_id = home_row[0]
    mod_rows = bind.execute(
        sa.text(
            "SELECT id, title FROM modules "
            "WHERE page_id = :pid AND deleted_at IS NULL "
            "AND json_extract(permissions, '$.pdash_default_example') = 1"
        ),
        {"pid": home_id},
    ).fetchall()
    modules_by_title = {row[1]: row[0] for row in mod_rows}
    return home_id, modules_by_title


def upgrade() -> None:
    now_s = _now()
    now_dt = datetime.now(UTC)
    bind = op.get_bind()

    home_id, modules_by_title = _resolve_home_context(bind)
    if home_id is None:
        op.execute(
            "INSERT INTO schema_migrations(version, applied_at, checksum) "
            f"VALUES ('0004_seed_example_approvals', '{now_s}', NULL)"
        )
        return

    bind.execute(
        sa.text(
            "DELETE FROM approval_requests "
            "WHERE idempotency_key LIKE :prefix"
        ),
        {"prefix": f"{IDEMPOTENCY_PREFIX}%"},
    )
    bind.execute(
        sa.text(
            "DELETE FROM agents "
            "WHERE json_extract(permissions, '$.pdash_default_example') = 1"
        )
    )

    agent_id = _new_id("agt")
    provisional_id = _new_id("mod")
    approval_specs = home_example_approvals(
        now_dt,
        home_page_id=home_id,
        modules_by_title=modules_by_title,
        provisional_id=provisional_id,
    )
    if not approval_specs:
        op.execute(
            "INSERT INTO schema_migrations(version, applied_at, checksum) "
            f"VALUES ('0004_seed_example_approvals', '{now_s}', NULL)"
        )
        return

    agents_table = sa.table(
        "agents",
        sa.column("id", sa.Text),
        sa.column("display_name", sa.Text),
        sa.column("description", sa.Text),
        sa.column("api_key_hash", sa.Text),
        sa.column("permissions", sa.Text),
        sa.column("status", sa.Text),
        sa.column("created_at", sa.Text),
        sa.column("last_active_at", sa.Text),
        sa.column("last_key_rotated_at", sa.Text),
    )
    op.bulk_insert(
        agents_table,
        [
            {
                "id": agent_id,
                "display_name": EXAMPLE_AGENT_DISPLAY_NAME,
                "description": EXAMPLE_AGENT_DESCRIPTION,
                "api_key_hash": hash_password(EXAMPLE_AGENT_KEY_PLAINTEXT),
                "permissions": json.dumps(EXAMPLE_AGENT_PERMISSIONS),
                "status": "active",
                "created_at": now_s,
                "last_active_at": None,
                "last_key_rotated_at": now_s,
            }
        ],
    )

    expires = expires_at(now_dt)
    apr_table = sa.table(
        "approval_requests",
        sa.column("id", sa.Text),
        sa.column("agent_id", sa.Text),
        sa.column("action_type", sa.Text),
        sa.column("target_kind", sa.Text),
        sa.column("target_id", sa.Text),
        sa.column("proposed_payload", sa.Text),
        sa.column("idempotency_key", sa.Text),
        sa.column("status", sa.Text),
        sa.column("created_at", sa.Text),
        sa.column("decided_at", sa.Text),
        sa.column("decided_by", sa.Text),
        sa.column("decision_reason", sa.Text),
        sa.column("applied_at", sa.Text),
        sa.column("executed_at", sa.Text),
        sa.column("execution_result", sa.Text),
        sa.column("expires_at", sa.Text),
    )
    op.bulk_insert(
        apr_table,
        [
            {
                "id": _new_id("apr"),
                "agent_id": agent_id,
                "action_type": spec["action_type"],
                "target_kind": spec["target_kind"],
                "target_id": spec["target_id"],
                "proposed_payload": json.dumps(
                    spec["proposed_payload"], separators=(",", ":"), default=str
                ),
                "idempotency_key": spec["idempotency_key"],
                "status": "pending",
                "created_at": now_s,
                "decided_at": None,
                "decided_by": None,
                "decision_reason": spec["decision_reason"],
                "applied_at": None,
                "executed_at": None,
                "execution_result": None,
                "expires_at": expires,
            }
            for spec in approval_specs
        ],
    )

    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0004_seed_example_approvals', '{now_s}', NULL)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM approval_requests "
            "WHERE idempotency_key LIKE :prefix"
        ),
        {"prefix": f"{IDEMPOTENCY_PREFIX}%"},
    )
    bind.execute(
        sa.text(
            "DELETE FROM agents "
            "WHERE json_extract(permissions, '$.pdash_default_example') = 1"
        )
    )
    op.execute("DELETE FROM schema_migrations WHERE version='0004_seed_example_approvals'")
