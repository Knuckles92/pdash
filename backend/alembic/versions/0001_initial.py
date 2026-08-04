"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-25
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from ulid import ULID

from alembic import op
from app.seed_home import SEED_VERSION, home_example_modules

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


# ---------------------------------------------------------------------------
# Default approval rules
# ---------------------------------------------------------------------------
DEFAULT_RULES = [
    # action_type, owner_scope, outcome
    ("update_module_data", "self", "auto_approve"),
    ("update_module_data", "other", "prompt"),
    ("update_module_config", "any", "prompt"),
    ("update_module_meta", "any", "prompt"),
    ("create_module", "any", "prompt"),
    ("delete_module", "any", "prompt"),
    ("create_page", "any", "prompt"),
    ("delete_page", "any", "prompt"),
    ("fire_action_button", "any", "prompt"),
    # `append_log` is a special-cased flavor of update_module_data for log_stream
    # — covered by the first rule above; we add a more-specific module_type rule
    # so admins can disable just the log_stream auto-approve if desired.
    # Stored with module_type='log_stream' to match the matcher's specificity.
]


def upgrade() -> None:
    # ------------------------------------------------------------------
    # kv_settings
    # ------------------------------------------------------------------
    op.create_table(
        "kv_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )

    # ------------------------------------------------------------------
    # agents
    # ------------------------------------------------------------------
    op.create_table(
        "agents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("api_key_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("permissions", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_active_at", sa.Text(), nullable=True),
        sa.Column("last_key_rotated_at", sa.Text(), nullable=True),
        sa.CheckConstraint("json_valid(permissions)", name="ck_agents_perm_json"),
        sa.CheckConstraint(
            "status IN ('active','disabled','revoked')", name="ck_agents_status"
        ),
    )

    # ------------------------------------------------------------------
    # pages
    # ------------------------------------------------------------------
    op.create_table(
        "pages",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("owner_kind", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('home','agent','custom','system')", name="ck_pages_kind"
        ),
        sa.CheckConstraint(
            "owner_kind IS NULL OR owner_kind IN ('user','agent')",
            name="ck_pages_owner_kind",
        ),
    )

    # ------------------------------------------------------------------
    # modules
    # ------------------------------------------------------------------
    op.create_table(
        "modules",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("owner_kind", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column(
            "page_id",
            sa.Text(),
            sa.ForeignKey("pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grid", sa.Text(), nullable=True),
        sa.Column("permissions", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("last_updated_by", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint("json_valid(permissions)", name="ck_modules_perm_json"),
        sa.CheckConstraint("grid IS NULL OR json_valid(grid)", name="ck_modules_grid_json"),
        sa.CheckConstraint("json_valid(data)", name="ck_modules_data_json"),
        sa.CheckConstraint("json_valid(config)", name="ck_modules_config_json"),
        sa.CheckConstraint(
            "type IN ('markdown','key_value','table','timeseries','log_stream',"
            "'link_list','iframe','action_button','notification')",
            name="ck_modules_type",
        ),
        sa.CheckConstraint("owner_kind IN ('user','agent')", name="ck_modules_owner_kind"),
    )
    op.execute(
        "CREATE INDEX idx_modules_page_position ON modules(page_id, position) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_modules_owner ON modules(owner_kind, owner_id) "
        "WHERE deleted_at IS NULL"
    )
    op.execute("CREATE INDEX idx_modules_type ON modules(type) WHERE deleted_at IS NULL")

    # ------------------------------------------------------------------
    # approval_requests
    # ------------------------------------------------------------------
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.Text(),
            sa.ForeignKey("agents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("proposed_payload", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.Text(), nullable=True),
        sa.Column("execution_result", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.Text(), nullable=True),
        sa.CheckConstraint("json_valid(proposed_payload)", name="ck_apr_payload_json"),
        sa.CheckConstraint(
            "execution_result IS NULL OR json_valid(execution_result)",
            name="ck_apr_exec_result_json",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','denied','applied','application_failed','superseded','expired')",
            name="ck_apr_status",
        ),
        sa.CheckConstraint(
            "target_kind IS NULL OR target_kind IN ('module','page','action_target')",
            name="ck_apr_target_kind",
        ),
    )
    op.execute(
        "CREATE INDEX idx_approvals_status_created ON approval_requests(status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_approvals_agent_created ON approval_requests(agent_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_approvals_target ON approval_requests(target_kind, target_id)"
    )

    # ------------------------------------------------------------------
    # approval_rules
    # ------------------------------------------------------------------
    op.create_table(
        "approval_rules",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("module_type", sa.Text(), nullable=True),
        sa.Column("module_id", sa.Text(), nullable=True),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("owner_scope", sa.Text(), nullable=False, server_default="any"),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_builtin", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("last_applied_at", sa.Text(), nullable=True),
        sa.Column("application_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "owner_scope IN ('any','self','other')", name="ck_rules_owner_scope"
        ),
        sa.CheckConstraint(
            "outcome IN ('auto_approve','deny','prompt')", name="ck_rules_outcome"
        ),
        sa.CheckConstraint("action_type != '*'", name="ck_rules_action_not_wild"),
    )
    op.execute(
        "CREATE INDEX idx_rules_lookup ON approval_rules"
        "(action_type, agent_id, module_type, module_id, page_id) WHERE enabled=1"
    )

    # ------------------------------------------------------------------
    # activity_log
    # ------------------------------------------------------------------
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("actor_kind", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("payload_summary", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column(
            "request_id",
            sa.Text(),
            sa.ForeignKey("approval_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rule_id", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "payload_summary IS NULL OR json_valid(payload_summary)",
            name="ck_activity_summary_json",
        ),
        sa.CheckConstraint(
            "actor_kind IN ('user','agent','system','rule')",
            name="ck_activity_actor_kind",
        ),
        sa.CheckConstraint(
            "outcome IN ('applied','queued','auto_approved','denied','error')",
            name="ck_activity_outcome",
        ),
    )
    op.execute("CREATE INDEX idx_activity_ts ON activity_log(timestamp DESC)")
    op.execute(
        "CREATE INDEX idx_activity_actor_ts ON activity_log(actor_kind, actor_id, timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX idx_activity_target ON activity_log(target_kind, target_id, timestamp DESC)"
    )
    op.execute("CREATE INDEX idx_activity_request ON activity_log(request_id)")

    # ------------------------------------------------------------------
    # iframe_allowlist (host_pattern + optional path_prefix per P0)
    # ------------------------------------------------------------------
    op.create_table(
        "iframe_allowlist",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("host_pattern", sa.Text(), nullable=False, unique=True),
        sa.Column("path_prefix", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("added_at", sa.Text(), nullable=False),
    )

    # ------------------------------------------------------------------
    # action_targets (mode column per P0)
    # ------------------------------------------------------------------
    op.create_table(
        "action_targets",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False, server_default="sync"),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint("json_valid(config)", name="ck_at_config_json"),
        sa.CheckConstraint(
            "kind IN ('webhook','local_script','mcp_tool','agent_message')",
            name="ck_at_kind",
        ),
        sa.CheckConstraint("mode IN ('sync','async')", name="ck_at_mode"),
    )

    # ------------------------------------------------------------------
    # agent_messages
    # ------------------------------------------------------------------
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("from_actor", sa.Text(), nullable=False),
        sa.Column(
            "to_agent_id",
            sa.Text(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("delivered_at", sa.Text(), nullable=True),
        sa.Column("read_at", sa.Text(), nullable=True),
        sa.CheckConstraint("json_valid(payload)", name="ck_am_payload_json"),
    )
    op.execute(
        "CREATE INDEX idx_agent_messages_inbox ON agent_messages(to_agent_id, delivered_at)"
    )

    # ------------------------------------------------------------------
    # audit_blobs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_blobs",
        sa.Column("sha256", sa.Text(), primary_key=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    # ------------------------------------------------------------------
    # request_idempotency
    # ------------------------------------------------------------------
    op.create_table(
        "request_idempotency",
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column(
            "request_id",
            sa.Text(),
            sa.ForeignKey("approval_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("response_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("agent_id", "tool", "key", name="pk_idem"),
        sa.CheckConstraint(
            "json_valid(response_snapshot)", name="ck_idem_snapshot_json"
        ),
    )

    # ------------------------------------------------------------------
    # schema_migrations
    # ------------------------------------------------------------------
    op.create_table(
        "schema_migrations",
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column("applied_at", sa.Text(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=True),
    )

    # ------------------------------------------------------------------
    # Seed: home page
    # ------------------------------------------------------------------
    now_dt = datetime.now(UTC)
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    home_id = _new_id("pg")
    pages_table = sa.table(
        "pages",
        sa.column("id", sa.Text),
        sa.column("slug", sa.Text),
        sa.column("name", sa.Text),
        sa.column("description", sa.Text),
        sa.column("kind", sa.Text),
        sa.column("owner_kind", sa.Text),
        sa.column("owner_id", sa.Text),
        sa.column("created_at", sa.Text),
    )
    op.bulk_insert(
        pages_table,
        [
            {
                "id": home_id,
                "slug": "home",
                "name": "Home",
                "description": "Default landing page.",
                "kind": "home",
                "owner_kind": None,
                "owner_id": None,
                "created_at": now,
            }
        ],
    )

    # ------------------------------------------------------------------
    # Seed: Home default example modules
    # ------------------------------------------------------------------
    modules_table = sa.table(
        "modules",
        sa.column("id", sa.Text),
        sa.column("type", sa.Text),
        sa.column("title", sa.Text),
        sa.column("owner_kind", sa.Text),
        sa.column("owner_id", sa.Text),
        sa.column("page_id", sa.Text),
        sa.column("position", sa.Integer),
        sa.column("grid", sa.Text),
        sa.column("permissions", sa.Text),
        sa.column("data", sa.Text),
        sa.column("config", sa.Text),
        sa.column("schema_version", sa.Integer),
        sa.column("version", sa.Integer),
        sa.column("created_at", sa.Text),
        sa.column("updated_at", sa.Text),
        sa.column("last_updated_by", sa.Text),
    )
    default_example_permissions = {
        "pdash_default_example": True,
        "seed_version": SEED_VERSION,
    }

    def module_row(spec: dict, position: int) -> dict:
        return {
            "id": _new_id("mod"),
            "type": spec["type"],
            "title": spec["title"],
            "owner_kind": "user",
            "owner_id": "admin",
            "page_id": home_id,
            "position": position,
            "grid": json.dumps({"colspan": spec.get("colspan", 1)}),
            "permissions": json.dumps(default_example_permissions),
            "data": json.dumps(spec["data"]),
            "config": json.dumps(spec["config"]),
            "schema_version": 1,
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "last_updated_by": "system:bootstrap",
        }

    # Seed only the module types this migration's own CHECK constraint allows.
    # Later migrations widen the constraint AND seed any tiles for newly added
    # types (see e.g. 0009_progress), so home_example_modules() may carry types
    # that 0001 cannot yet insert.
    _seed_types = {
        "markdown", "key_value", "table", "timeseries", "log_stream",
        "link_list", "iframe", "action_button", "notification",
    }
    _seed_specs = [
        spec for spec in home_example_modules(now_dt) if spec["type"] in _seed_types
    ]
    op.bulk_insert(
        modules_table,
        [module_row(spec, i) for i, spec in enumerate(_seed_specs)],
    )

    # ------------------------------------------------------------------
    # Seed: built-in approval rules
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
                "action_type": action_type,
                "module_type": None,
                "module_id": None,
                "page_id": None,
                "owner_scope": owner_scope,
                "outcome": outcome,
                "priority": 200,
                "is_builtin": 1,
                "enabled": 1,
                "notes": f"Built-in default rule for {action_type}/{owner_scope}.",
                "created_at": now,
                "created_by": "system:bootstrap",
                "application_count": 0,
            }
            for action_type, owner_scope, outcome in DEFAULT_RULES
        ],
    )

    # Record this migration
    sm_table = sa.table(
        "schema_migrations",
        sa.column("version", sa.Text),
        sa.column("applied_at", sa.Text),
        sa.column("checksum", sa.Text),
    )
    op.bulk_insert(
        sm_table,
        [{"version": "0001_initial", "applied_at": now, "checksum": None}],
    )


def downgrade() -> None:
    op.drop_table("schema_migrations")
    op.drop_table("request_idempotency")
    op.drop_table("audit_blobs")
    op.drop_table("agent_messages")
    op.drop_table("action_targets")
    op.drop_table("iframe_allowlist")
    op.drop_table("activity_log")
    op.drop_table("approval_rules")
    op.drop_table("approval_requests")
    op.drop_table("modules")
    op.drop_table("pages")
    op.drop_table("agents")
    op.drop_table("kv_settings")
