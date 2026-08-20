"""Re-gate built-in approval rules by risk.

Revision ID: 0012_approval_risk_defaults
Revises: 0011_pages_kind_to_type
Create Date: 2026-08-19

Owner create/config/meta auto-approve; html/iframe/action_button create still
prompt; html content updates fall back to self-owned data auto-approve;
fire_action self auto-approves; seed update_module_capability → prompt;
backfill page-access free/blocked sets with the new action type.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from ulid import ULID

from alembic import op

revision: str = "0012_approval_risk_defaults"
down_revision: str | Sequence[str] | None = "0011_pages_kind_to_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAGE_ACCESS_TYPES = (
    "create_module",
    "update_module_data",
    "update_module_config",
    "update_module_meta",
    "delete_module",
)
NEW_ACCESS_TYPE = "update_module_capability"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def upgrade() -> None:
    conn = op.get_bind()
    now_s = _now()

    # Disable the 0010 html-always-prompt builtin so owner iterates auto-apply.
    conn.execute(
        sa.text(
            "UPDATE approval_rules SET enabled = 0 "
            "WHERE is_builtin = 1 AND action_type = 'update_module_data' "
            "AND module_type = 'html'"
        )
    )

    def _has_builtin(*, action_type: str, owner_scope: str, module_type: str | None) -> bool:
        if module_type is None:
            row = conn.execute(
                sa.text(
                    "SELECT 1 FROM approval_rules WHERE is_builtin = 1 "
                    "AND action_type = :a AND owner_scope = :o AND module_type IS NULL "
                    "LIMIT 1"
                ),
                {"a": action_type, "o": owner_scope},
            ).fetchone()
        else:
            row = conn.execute(
                sa.text(
                    "SELECT 1 FROM approval_rules WHERE is_builtin = 1 "
                    "AND action_type = :a AND owner_scope = :o AND module_type = :m "
                    "LIMIT 1"
                ),
                {"a": action_type, "o": owner_scope, "m": module_type},
            ).fetchone()
        return row is not None

    def _insert(
        *,
        action_type: str,
        owner_scope: str,
        outcome: str,
        notes: str,
        module_type: str | None = None,
    ) -> None:
        if _has_builtin(
            action_type=action_type, owner_scope=owner_scope, module_type=module_type
        ):
            return
        conn.execute(
            sa.text(
                "INSERT INTO approval_rules("
                "id, agent_id, action_type, module_type, module_id, page_id, "
                "owner_scope, outcome, priority, is_builtin, enabled, notes, "
                "created_at, created_by, application_count"
                ") VALUES ("
                ":id, '*', :action_type, :module_type, NULL, NULL, "
                ":owner_scope, :outcome, 200, 1, 1, :notes, "
                ":created_at, 'system:bootstrap', 0)"
            ),
            {
                "id": _new_id("rule"),
                "action_type": action_type,
                "module_type": module_type,
                "owner_scope": owner_scope,
                "outcome": outcome,
                "notes": notes,
                "created_at": now_s,
            },
        )

    _insert(
        action_type="create_module",
        owner_scope="self",
        outcome="auto_approve",
        notes="Built-in: owner create on a page the agent owns (not home/system).",
    )
    for mtype in ("html", "iframe", "action_button"):
        _insert(
            action_type="create_module",
            owner_scope="any",
            outcome="prompt",
            module_type=mtype,
            notes=f"Built-in: first {mtype} module still prompts.",
        )
    _insert(
        action_type="update_module_config",
        owner_scope="self",
        outcome="auto_approve",
        notes="Built-in: owner config (appearance, layout) auto-approves.",
    )
    _insert(
        action_type="update_module_meta",
        owner_scope="self",
        outcome="auto_approve",
        notes="Built-in: owner title/position/grid auto-approves.",
    )
    _insert(
        action_type="update_module_capability",
        owner_scope="any",
        outcome="prompt",
        notes="Built-in: capability-shaped fields (iframe src, button target, "
        "table columns, sandbox loosening, confirm true→false) always prompt.",
    )
    _insert(
        action_type="fire_action_button",
        owner_scope="self",
        outcome="auto_approve",
        notes="Built-in: firing an already-approved button the agent owns.",
    )

    # Backfill managed free/blocked sets so they stay complete after the new type.
    from collections import defaultdict

    managed_rows = conn.execute(
        sa.text(
            "SELECT agent_id, page_id, action_type, outcome FROM approval_rules "
            "WHERE is_builtin = 0 AND module_type IS NULL AND module_id IS NULL "
            "AND owner_scope = 'any' AND enabled = 1 AND page_id IS NOT NULL "
            "AND action_type IN "
            "('create_module','update_module_data','update_module_config',"
            "'update_module_meta','delete_module','update_module_capability')"
        )
    ).fetchall()
    groups: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for agent_id, page_id, action_type, outcome in managed_rows:
        groups[(agent_id, page_id)].append((action_type, outcome))
    old_set = set(PAGE_ACCESS_TYPES)
    for (agent_id, page_id), entries in groups.items():
        types = {t for t, _ in entries}
        outcomes = {o for _, o in entries}
        if types != old_set:
            continue
        if outcomes not in ({"auto_approve"}, {"deny"}):
            continue
        outcome = next(iter(outcomes))
        conn.execute(
            sa.text(
                "INSERT INTO approval_rules("
                "id, agent_id, action_type, module_type, module_id, page_id, "
                "owner_scope, outcome, priority, is_builtin, enabled, notes, "
                "created_at, created_by, application_count"
                ") VALUES ("
                ":id, :agent_id, :action_type, NULL, NULL, :page_id, "
                "'any', :outcome, 100, 0, 1, :notes, "
                ":created_at, 'system:migrate-0012', 0)"
            ),
            {
                "id": _new_id("rule"),
                "agent_id": agent_id,
                "action_type": NEW_ACCESS_TYPE,
                "page_id": page_id,
                "outcome": outcome,
                "notes": "Page access: backfilled update_module_capability",
                "created_at": now_s,
            },
        )

    conn.execute(
        sa.text(
            "INSERT INTO schema_migrations(version, applied_at, checksum) "
            "VALUES ('0012_approval_risk_defaults', :now, NULL)"
        ),
        {"now": now_s},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM approval_rules WHERE is_builtin = 1 AND ("
            "(action_type = 'create_module' AND owner_scope = 'self') OR "
            "(action_type = 'create_module' AND module_type IN "
            "('html','iframe','action_button')) OR "
            "(action_type = 'update_module_config' AND owner_scope = 'self') OR "
            "(action_type = 'update_module_meta' AND owner_scope = 'self') OR "
            "(action_type = 'update_module_capability') OR "
            "(action_type = 'fire_action_button' AND owner_scope = 'self')"
            ")"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM approval_rules WHERE created_by = 'system:migrate-0012'"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE approval_rules SET enabled = 1 "
            "WHERE is_builtin = 1 AND action_type = 'update_module_data' "
            "AND module_type = 'html'"
        )
    )
    conn.execute(
        sa.text("DELETE FROM schema_migrations WHERE version='0012_approval_risk_defaults'")
    )
