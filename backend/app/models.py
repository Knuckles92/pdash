"""SQLAlchemy 2.0 ORM models. Mirrors PLAN §3."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .timefmt import utcnow_iso as utcnow_iso  # re-exported for callers; impl in timefmt


class Base(DeclarativeBase):
    """Declarative base."""


# ---------------------------------------------------------------------------
# Auth / settings (not in PLAN §3 but required to bootstrap admin)
# ---------------------------------------------------------------------------


class KVSetting(Base):
    __tablename__ = "kv_settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    permissions: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'{}'"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_active_at: Mapped[str | None] = mapped_column(Text)
    last_key_rotated_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("json_valid(permissions)", name="ck_agents_perm_json"),
        CheckConstraint(
            "status IN ('active','disabled','revoked')", name="ck_agents_status",
        ),
    )


class AgentRegistrationRequest(Base):
    """A keyless AI client's request to become a registered agent.

    Created by the ungated MCP bootstrap surface (``api/internal_bootstrap.py``).
    Always lands ``pending`` in the Approvals inbox (``register_agent`` action) —
    we never auto-mint a key. On approval + claim a real :class:`Agent` row is
    minted; ``agent_id`` then links the two. Only a sha256 of the one-time claim
    token is stored (``claim_token_hash``); no agent key ever lives here.
    """

    __tablename__ = "agent_registration_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    requested_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    client_hint: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'"),
    )
    claim_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    permissions: Mapped[str | None] = mapped_column(Text)
    agent_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("agents.id", ondelete="SET NULL"),
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','denied','claimed','expired')",
            name="ck_areg_status",
        ),
        CheckConstraint(
            "permissions IS NULL OR json_valid(permissions)",
            name="ck_areg_perm_json",
        ),
        Index(
            "ux_areg_claim_token", "claim_token_hash", unique=True,
        ),
        Index("idx_areg_status_created", "status", text("created_at DESC")),
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    owner_kind: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "type IN ('home','agent','custom','system','corkboard','canvas')",
            name="ck_pages_type",
        ),
        CheckConstraint(
            "owner_kind IS NULL OR owner_kind IN ('user','agent')",
            name="ck_pages_owner_kind",
        ),
    )


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    owner_kind: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str] = mapped_column(Text, nullable=False)
    page_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    grid: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    data: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    config: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_updated_by: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("json_valid(permissions)", name="ck_modules_perm_json"),
        CheckConstraint(
            "grid IS NULL OR json_valid(grid)", name="ck_modules_grid_json",
        ),
        CheckConstraint("json_valid(data)", name="ck_modules_data_json"),
        CheckConstraint("json_valid(config)", name="ck_modules_config_json"),
        CheckConstraint(
            "type IN ('markdown','key_value','table','timeseries','log_stream',"
            "'link_list','iframe','action_button','notification','file','sticky_note',"
            "'progress','html')",
            name="ck_modules_type",
        ),
        CheckConstraint(
            "owner_kind IN ('user','agent')", name="ck_modules_owner_kind",
        ),
        Index(
            "idx_modules_page_position",
            "page_id",
            "position",
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_modules_owner",
            "owner_kind",
            "owner_id",
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_modules_type",
            "type",
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )


# ---------------------------------------------------------------------------
# Approval requests
# ---------------------------------------------------------------------------


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    proposed_payload: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'"),
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    # applied_at: when the approved mutation was written to state.
    # executed_at / execution_result: when an action_target side-effect finished
    # running (status stays 'applied'); see approval/lifecycle.py.
    applied_at: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[str | None] = mapped_column(Text)
    execution_result: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "json_valid(proposed_payload)", name="ck_apr_payload_json",
        ),
        CheckConstraint(
            "execution_result IS NULL OR json_valid(execution_result)",
            name="ck_apr_exec_result_json",
        ),
        CheckConstraint(
            "status IN ('pending','approved','denied','applied','application_failed','superseded','expired')",
            name="ck_apr_status",
        ),
        CheckConstraint(
            "target_kind IS NULL OR target_kind IN "
            "('module','page','action_target','agent_registration')",
            name="ck_apr_target_kind",
        ),
        Index("idx_approvals_status_created", "status", text("created_at DESC")),
        Index("idx_approvals_agent_created", "agent_id", text("created_at DESC")),
        Index("idx_approvals_target", "target_kind", "target_id"),
    )


# ---------------------------------------------------------------------------
# Approval rules
# ---------------------------------------------------------------------------


class ApprovalRule(Base):
    __tablename__ = "approval_rules"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    module_type: Mapped[str | None] = mapped_column(Text)
    module_id: Mapped[str | None] = mapped_column(Text)
    page_id: Mapped[str | None] = mapped_column(Text)
    owner_scope: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'any'"),
    )
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    last_applied_at: Mapped[str | None] = mapped_column(Text)
    application_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )

    __table_args__ = (
        CheckConstraint(
            "owner_scope IN ('any','self','other')", name="ck_rules_owner_scope",
        ),
        CheckConstraint(
            "outcome IN ('auto_approve','deny','prompt')", name="ck_rules_outcome",
        ),
        CheckConstraint("action_type != '*'", name="ck_rules_action_not_wild"),
        Index(
            "idx_rules_lookup",
            "action_type",
            "agent_id",
            "module_type",
            "module_id",
            "page_id",
            sqlite_where=text("enabled=1"),
        ),
    )


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    payload_summary: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("approval_requests.id", ondelete="SET NULL"),
    )
    rule_id: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "payload_summary IS NULL OR json_valid(payload_summary)",
            name="ck_activity_summary_json",
        ),
        CheckConstraint(
            "actor_kind IN ('user','agent','system','rule')",
            name="ck_activity_actor_kind",
        ),
        CheckConstraint(
            "outcome IN ('applied','queued','auto_approved','denied','error')",
            name="ck_activity_outcome",
        ),
        Index("idx_activity_ts", text("timestamp DESC")),
        Index("idx_activity_actor_ts", "actor_kind", "actor_id", text("timestamp DESC")),
        Index("idx_activity_target", "target_kind", "target_id", text("timestamp DESC")),
        Index("idx_activity_request", "request_id"),
    )


# ---------------------------------------------------------------------------
# Iframe allowlist (host + optional path prefix per P0 decision)
# ---------------------------------------------------------------------------


class IframeAllowlist(Base):
    __tablename__ = "iframe_allowlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_pattern: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    path_prefix: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------------------
# Action targets
# ---------------------------------------------------------------------------


class ActionTarget(Base):
    __tablename__ = "action_targets"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False)
    # P0 decision: sync/async is a property of the target row.
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'sync'"))
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("json_valid(config)", name="ck_at_config_json"),
        CheckConstraint(
            "kind IN ('webhook','local_script','mcp_tool','agent_message')",
            name="ck_at_kind",
        ),
        CheckConstraint("mode IN ('sync','async')", name="ck_at_mode"),
    )


# ---------------------------------------------------------------------------
# Agent messages
# ---------------------------------------------------------------------------


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    from_actor: Mapped[str] = mapped_column(Text, nullable=False)
    to_agent_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    delivered_at: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("json_valid(payload)", name="ck_am_payload_json"),
        Index("idx_agent_messages_inbox", "to_agent_id", "delivered_at"),
    )


# ---------------------------------------------------------------------------
# Files (agent file-drop)
# ---------------------------------------------------------------------------


class FileRecord(Base):
    """A file an agent dropped into the inbox and registered.

    On apply, the bytes are moved from the inbox into the managed store at
    ``<store>/<id>/blob`` and ``stored_path`` is set. ``page_id`` is an optional
    hint of the dashboard the file is intended for; the authoritative "where
    used" is whichever ``file`` module references this id in its data.
    """

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Null when the admin manually registers an orphaned inbox file (no agent).
    agent_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("agents.id", ondelete="SET NULL"),
    )
    inbox_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'registered'"),
    )
    page_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("pages.id", ondelete="SET NULL"),
    )
    purpose: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('registered','deleted')", name="ck_files_status"),
        CheckConstraint("kind IN ('image','document')", name="ck_files_kind"),
        CheckConstraint("size_bytes >= 0", name="ck_files_size"),
        Index("idx_files_agent", "agent_id", sqlite_where=text("deleted_at IS NULL")),
        Index("idx_files_page", "page_id"),
        Index("idx_files_sha", "sha256"),
    )


# ---------------------------------------------------------------------------
# Audit blobs
# ---------------------------------------------------------------------------


class AuditBlob(Base):
    __tablename__ = "audit_blobs"

    sha256: Mapped[str] = mapped_column(Text, primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------------------
# Request idempotency
# ---------------------------------------------------------------------------


class RequestIdempotency(Base):
    __tablename__ = "request_idempotency"

    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("approval_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    response_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("agent_id", "tool", "key", name="pk_idem"),
        CheckConstraint(
            "json_valid(response_snapshot)", name="ck_idem_snapshot_json",
        ),
    )


# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[str] = mapped_column(Text, primary_key=True)
    applied_at: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Agent rate limits (Phase 6 — persistent token buckets)
# ---------------------------------------------------------------------------


class AgentRateLimit(Base):
    __tablename__ = "agent_rate_limits"

    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_class: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[float] = mapped_column(Float, nullable=False)
    last_refill: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("agent_id", "action_class", name="pk_agent_rate_limits"),
        CheckConstraint(
            "action_class IN ('read','write')", name="ck_arl_action_class",
        ),
    )


__all__ = [
    "Base",
    "Agent",
    "AgentRegistrationRequest",
    "Page",
    "Module",
    "ApprovalRequest",
    "ApprovalRule",
    "ActivityLog",
    "IframeAllowlist",
    "ActionTarget",
    "AgentMessage",
    "FileRecord",
    "AuditBlob",
    "RequestIdempotency",
    "SchemaMigration",
    "AgentRateLimit",
    "KVSetting",
    "utcnow_iso",
]
