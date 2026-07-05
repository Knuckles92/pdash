"""register_agent approval type + nullable agent_id on approval_requests

Revision ID: 0007_register_agent_approvals
Revises: 0006_agent_registrations
Create Date: 2026-06-14

Wires agent self-registration into the approval engine:

- ``approval_requests.agent_id`` nullable (no agent exists yet).
- ``target_kind`` CHECK widened to allow ``agent_registration``.
- Built-in ``register_agent -> prompt`` rule.
- Backfill ``approval_requests`` rows for any pending registrations.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from ulid import ULID

from alembic import op

revision: str = "0007_register_agent_approvals"
down_revision: str | Sequence[str] | None = "0006_agent_registrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_TARGET_KIND = (
    "target_kind IS NULL OR target_kind IN ('module','page','action_target')"
)
_NEW_TARGET_KIND = (
    "target_kind IS NULL OR target_kind IN "
    "('module','page','action_target','agent_registration')"
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def upgrade() -> None:
    now_s = _now()

    # Manual table rebuild avoids SQLite batch_alter_table lock issues on FK children.
    op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_approval_requests"))
    op.execute(
        sa.text(
            """
            CREATE TABLE approval_requests_v7 (
                id TEXT NOT NULL PRIMARY KEY,
                agent_id TEXT REFERENCES agents(id) ON DELETE RESTRICT,
                action_type TEXT NOT NULL,
                target_kind TEXT,
                target_id TEXT,
                proposed_payload TEXT NOT NULL,
                idempotency_key TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                decision_reason TEXT,
                applied_at TEXT,
                executed_at TEXT,
                execution_result TEXT,
                expires_at TEXT,
                CONSTRAINT ck_apr_payload_json CHECK (json_valid(proposed_payload)),
                CONSTRAINT ck_apr_exec_result_json CHECK (
                    execution_result IS NULL OR json_valid(execution_result)
                ),
                CONSTRAINT ck_apr_status CHECK (
                    status IN (
                        'pending','approved','denied','applied',
                        'application_failed','superseded','expired'
                    )
                ),
                CONSTRAINT ck_apr_target_kind CHECK (
                    target_kind IS NULL OR target_kind IN (
                        'module','page','action_target','agent_registration'
                    )
                )
            )
            """
        )
    )
    op.execute(sa.text("INSERT INTO approval_requests_v7 SELECT * FROM approval_requests"))
    op.execute(sa.text("DROP TABLE approval_requests"))
    op.execute(sa.text("ALTER TABLE approval_requests_v7 RENAME TO approval_requests"))
    op.execute(
        sa.text(
            "CREATE INDEX idx_approvals_status_created "
            "ON approval_requests(status, created_at DESC)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX idx_approvals_agent_created "
            "ON approval_requests(agent_id, created_at DESC)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX idx_approvals_target "
            "ON approval_requests(target_kind, target_id)"
        )
    )
    op.execute(sa.text("PRAGMA foreign_keys=ON"))

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
                "action_type": "register_agent",
                "module_type": None,
                "module_id": None,
                "page_id": None,
                "owner_scope": "any",
                "outcome": "prompt",
                "priority": 200,
                "is_builtin": 1,
                "enabled": 1,
                "notes": "Built-in default rule for register_agent/any.",
                "created_at": now_s,
                "created_by": "system:bootstrap",
                "application_count": 0,
            }
        ],
    )

    conn = op.get_bind()
    pending = conn.execute(
        sa.text(
            "SELECT id, requested_name, description, rationale, client_hint, "
            "created_at, expires_at FROM agent_registration_requests "
            "WHERE status = 'pending'"
        )
    ).fetchall()
    for row in pending:
        areg_id = row[0]
        linked = conn.execute(
            sa.text(
                "SELECT 1 FROM approval_requests "
                "WHERE action_type = 'register_agent' AND target_id = :tid"
            ),
            {"tid": areg_id},
        ).fetchone()
        if linked is not None:
            continue
        payload = json.dumps(
            {
                "display_name": row[1],
                "description": row[2],
                "rationale": row[3],
                "client_hint": row[4],
            },
            separators=(",", ":"),
        )
        apr_id = _new_id("apr")
        conn.execute(
            sa.text(
                "INSERT INTO approval_requests "
                "(id, agent_id, action_type, target_kind, target_id, proposed_payload, "
                "status, created_at, expires_at) "
                "VALUES (:id, NULL, 'register_agent', 'agent_registration', :target_id, "
                ":payload, 'pending', :created_at, :expires_at)"
            ),
            {
                "id": apr_id,
                "target_id": areg_id,
                "payload": payload,
                "created_at": row[5],
                "expires_at": row[6],
            },
        )

    op.execute(
        "INSERT INTO schema_migrations(version, applied_at, checksum) "
        f"VALUES ('0007_register_agent_approvals', '{now_s}', NULL)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM approval_requests WHERE action_type = 'register_agent'")
    )
    conn.execute(
        sa.text("DELETE FROM approval_rules WHERE action_type = 'register_agent'")
    )
    op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    op.execute(
        sa.text(
            """
            CREATE TABLE approval_requests_v6 (
                id TEXT NOT NULL PRIMARY KEY,
                agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
                action_type TEXT NOT NULL,
                target_kind TEXT,
                target_id TEXT,
                proposed_payload TEXT NOT NULL,
                idempotency_key TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                decision_reason TEXT,
                applied_at TEXT,
                executed_at TEXT,
                execution_result TEXT,
                expires_at TEXT,
                CONSTRAINT ck_apr_payload_json CHECK (json_valid(proposed_payload)),
                CONSTRAINT ck_apr_exec_result_json CHECK (
                    execution_result IS NULL OR json_valid(execution_result)
                ),
                CONSTRAINT ck_apr_status CHECK (
                    status IN (
                        'pending','approved','denied','applied',
                        'application_failed','superseded','expired'
                    )
                ),
                CONSTRAINT ck_apr_target_kind CHECK (
                    target_kind IS NULL OR target_kind IN ('module','page','action_target')
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO approval_requests_v6 "
            "SELECT * FROM approval_requests WHERE agent_id IS NOT NULL"
        )
    )
    op.execute(sa.text("DROP TABLE approval_requests"))
    op.execute(sa.text("ALTER TABLE approval_requests_v6 RENAME TO approval_requests"))
    op.execute(
        sa.text(
            "CREATE INDEX idx_approvals_status_created "
            "ON approval_requests(status, created_at DESC)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX idx_approvals_agent_created "
            "ON approval_requests(agent_id, created_at DESC)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX idx_approvals_target "
            "ON approval_requests(target_kind, target_id)"
        )
    )
    op.execute(sa.text("PRAGMA foreign_keys=ON"))
