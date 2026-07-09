"""Approval engine schemas: requests, rules, and helper drafts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# ApprovalRequest output
# ---------------------------------------------------------------------------


class ApprovalRequestOut(BaseModel):
    id: str
    agent_id: str | None = None
    action_type: str
    target_kind: str | None = None
    target_id: str | None = None
    proposed_payload: dict[str, Any]
    idempotency_key: str | None = None
    status: str
    created_at: str
    decided_at: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    applied_at: str | None = None
    executed_at: str | None = None
    execution_result: dict[str, Any] | None = None
    expires_at: str | None = None


class ApprovalRequestListOut(BaseModel):
    items: list[ApprovalRequestOut]
    next_cursor: str | None = None
    total_pending: int | None = None


class ApprovalRequestDetailOut(ApprovalRequestOut):
    """Includes a preview of the proposed change when applicable.

    At most one of the ``*_preview`` fields is populated, keyed off the
    request's ``action_type`` (module/page changes → ``dashboard_preview``,
    fire_action_button → ``action_preview``, register_file → ``file_preview``,
    register_agent → ``registration_preview``).
    """

    diff_preview: dict[str, Any] | None = None
    dashboard_preview: dict[str, Any] | None = None
    action_preview: dict[str, Any] | None = None
    file_preview: dict[str, Any] | None = None
    registration_preview: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Approve / Deny bodies
# ---------------------------------------------------------------------------


class ApprovalRuleDraft(BaseModel):
    """Draft of a rule to be created from an approval decision.

    Field semantics mirror ``approval_rules`` columns. ``apply_to_pending``
    triggers a retroactive sweep of matching pending requests through the
    engine in the same transaction (default off; the UI surfaces
    a checkbox).
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str = "*"
    action_type: str
    module_type: str | None = None
    module_id: str | None = None
    page_id: str | None = None
    owner_scope: Literal["any", "self", "other"] = "any"
    outcome: Literal["auto_approve", "deny", "prompt"]
    priority: int = 100
    notes: str | None = None
    enabled: bool = True
    apply_to_pending: bool = False


class RegistrationApproveOverrides(BaseModel):
    """Optional admin overrides when approving a ``register_agent`` request."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permissions: dict[str, Any] | None = None


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    create_rule: ApprovalRuleDraft | None = None
    registration: RegistrationApproveOverrides | None = None


class DenyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    create_rule: ApprovalRuleDraft | None = None


class BulkDecisionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    decision: Literal["approve", "deny"]
    reason: str | None = None


class BulkDecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[BulkDecisionItem] = Field(..., min_length=1, max_length=50)


class BulkDecisionResult(BaseModel):
    id: str
    status: str
    error: str | None = None


class BulkDecideOut(BaseModel):
    results: list[BulkDecisionResult]


# ---------------------------------------------------------------------------
# Approval rules CRUD
# ---------------------------------------------------------------------------


class ApprovalRuleOut(BaseModel):
    id: str
    agent_id: str
    action_type: str
    module_type: str | None = None
    module_id: str | None = None
    page_id: str | None = None
    owner_scope: str
    outcome: str
    priority: int
    is_builtin: bool
    enabled: bool
    notes: str | None = None
    created_at: str
    created_by: str
    last_applied_at: str | None = None
    application_count: int


class ApprovalRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = "*"
    action_type: str
    module_type: str | None = None
    module_id: str | None = None
    page_id: str | None = None
    owner_scope: Literal["any", "self", "other"] = "any"
    outcome: Literal["auto_approve", "deny", "prompt"]
    priority: int = 100
    notes: str | None = None
    enabled: bool = True
    apply_to_pending: bool = False


class ApprovalRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str | None = None
    module_type: str | None = None
    module_id: str | None = None
    page_id: str | None = None
    owner_scope: Literal["any", "self", "other"] | None = None
    outcome: Literal["auto_approve", "deny", "prompt"] | None = None
    priority: int | None = None
    notes: str | None = None
    enabled: bool | None = None
