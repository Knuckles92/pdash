"""Admin endpoints for ``/api/v1/approval-rules/*``."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..approval import bump_rules_version
from ..approval.engine import CachedRule, DecisionRequest, _rule_matches
from ..auth.deps import CurrentUser, require_csrf, require_session
from ..db import get_session, read_session
from ..errors import forbidden, not_found
from ..ids import new_id
from ..models import ApprovalRequest, ApprovalRule, Module, Page, utcnow_iso
from ..schemas import (
    ApprovalRuleCreate,
    ApprovalRuleOut,
    ApprovalRuleUpdate,
    CursorPage,
)
from ..services.audit import write_event
from ..timefmt import iso_millis

router = APIRouter(prefix="/api/v1/approval-rules", tags=["approval-rules"])

# Built-in rules can be disabled but not have their scope/outcome rewired;
# these fields are immutable on a built-in rule.
BUILTIN_IMMUTABLE_FIELDS = (
    "agent_id",
    "module_type",
    "module_id",
    "page_id",
    "owner_scope",
    "outcome",
)


def _to_out(row: ApprovalRule) -> ApprovalRuleOut:
    return ApprovalRuleOut(
        id=row.id,
        agent_id=row.agent_id,
        action_type=row.action_type,
        module_type=row.module_type,
        module_id=row.module_id,
        page_id=row.page_id,
        owner_scope=row.owner_scope,
        outcome=row.outcome,
        priority=row.priority,
        is_builtin=bool(row.is_builtin),
        enabled=bool(row.enabled),
        notes=row.notes,
        created_at=row.created_at,
        created_by=row.created_by,
        last_applied_at=row.last_applied_at,
        application_count=row.application_count,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=CursorPage[ApprovalRuleOut])
async def list_rules(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
    enabled: bool | None = None,
    agent_id: str | None = None,
    action_type: str | None = None,
    page_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> CursorPage[ApprovalRuleOut]:
    stmt = select(ApprovalRule)
    if enabled is not None:
        stmt = stmt.where(ApprovalRule.enabled == (1 if enabled else 0))
    if agent_id:
        stmt = stmt.where(ApprovalRule.agent_id == agent_id)
    if action_type:
        stmt = stmt.where(ApprovalRule.action_type == action_type)
    if page_id:
        stmt = stmt.where(ApprovalRule.page_id == page_id)
    if cursor:
        stmt = stmt.where(ApprovalRule.id > cursor)
    # Sort by priority asc for the UI surface.
    stmt = stmt.order_by(ApprovalRule.priority, ApprovalRule.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    next_cursor = rows[limit].id if len(rows) > limit else None
    return CursorPage[ApprovalRuleOut](
        items=[_to_out(r) for r in rows[:limit]],
        next_cursor=next_cursor,
    )


# ---------------------------------------------------------------------------
# Get one
# ---------------------------------------------------------------------------


@router.get("/{rule_id}", response_model=ApprovalRuleOut)
async def get_rule(
    rule_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> ApprovalRuleOut:
    row = await session.get(ApprovalRule, rule_id)
    if row is None:
        raise not_found("approval_rule.not_found", rule_id)
    return _to_out(row)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_rule(
    body: ApprovalRuleCreate,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    row = ApprovalRule(
        id=new_id("rule"),
        agent_id=body.agent_id,
        action_type=body.action_type,
        module_type=body.module_type,
        module_id=body.module_id,
        page_id=body.page_id,
        owner_scope=body.owner_scope,
        outcome=body.outcome,
        priority=body.priority,
        is_builtin=0,
        enabled=1 if body.enabled else 0,
        notes=body.notes,
        created_at=utcnow_iso(),
        created_by=f"admin:{user.name}",
        application_count=0,
    )
    session.add(row)
    await session.flush()
    bump_rules_version()
    await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type="create_approval_rule",
        target_kind="approval_rule",
        target_id=row.id,
        outcome="applied",
        payload_summary={
            "rule_action_type": body.action_type,
            "outcome": body.outcome,
            "owner_scope": body.owner_scope,
        },
        rule_id=row.id,
    )

    applied_to_pending = 0
    if body.apply_to_pending:
        from .approval_requests import _apply_to_pending
        applied_to_pending = await _apply_to_pending(
            session, action_type=body.action_type, actor=f"admin:{user.name}"
        )

    return {"rule": _to_out(row).model_dump(), "applied_to_pending": applied_to_pending}


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@router.patch("/{rule_id}", response_model=ApprovalRuleOut)
async def update_rule(
    rule_id: str,
    body: ApprovalRuleUpdate,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApprovalRuleOut:
    row = await session.get(ApprovalRule, rule_id)
    if row is None:
        raise not_found("approval_rule.not_found", rule_id)
    changed_fields = body.model_fields_set
    # Built-ins can be disabled but not have their scope/outcome rewired.
    if row.is_builtin:
        for immutable_field in BUILTIN_IMMUTABLE_FIELDS:
            val = getattr(body, immutable_field, None)
            if immutable_field in changed_fields and getattr(row, immutable_field) != val:
                raise forbidden(
                    "approval_rule.builtin_immutable",
                    f"Cannot modify {immutable_field} on a built-in rule",
                )
    if body.agent_id is not None:
        row.agent_id = body.agent_id
    if "module_type" in changed_fields:
        row.module_type = body.module_type
    if "module_id" in changed_fields:
        row.module_id = body.module_id
    if "page_id" in changed_fields:
        row.page_id = body.page_id
    if body.owner_scope is not None:
        row.owner_scope = body.owner_scope
    if body.outcome is not None:
        row.outcome = body.outcome
    if body.priority is not None:
        row.priority = body.priority
    if "notes" in changed_fields:
        row.notes = body.notes
    if body.enabled is not None:
        row.enabled = 1 if body.enabled else 0
    await session.flush()
    bump_rules_version()
    await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type="update_approval_rule",
        target_kind="approval_rule",
        target_id=row.id,
        outcome="applied",
        rule_id=row.id,
    )
    return _to_out(row)


# ---------------------------------------------------------------------------
# Delete (disallowed on builtins)
# ---------------------------------------------------------------------------


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    row = await session.get(ApprovalRule, rule_id)
    if row is None:
        raise not_found("approval_rule.not_found", rule_id)
    if row.is_builtin:
        raise forbidden(
            "approval_rule.builtin_cannot_delete",
            "Built-in rules can be disabled but not deleted",
        )
    await session.delete(row)
    await session.flush()
    bump_rules_version()
    await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type="delete_approval_rule",
        target_kind="approval_rule",
        target_id=rule_id,
        outcome="applied",
        rule_id=rule_id,
    )
    return None


# ---------------------------------------------------------------------------
# Preview — dry-run against historical approval_requests
# ---------------------------------------------------------------------------


@router.post("/{rule_id}/preview")
async def preview_rule(
    rule_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    row = await session.get(ApprovalRule, rule_id)
    if row is None:
        raise not_found("approval_rule.not_found", rule_id)

    cached = CachedRule(
        id=row.id,
        agent_id=row.agent_id,
        action_type=row.action_type,
        module_type=row.module_type,
        module_id=row.module_id,
        page_id=row.page_id,
        owner_scope=row.owner_scope,
        outcome=row.outcome,
        priority=row.priority,
        is_builtin=bool(row.is_builtin),
        created_at=row.created_at,
    )
    # Look at all historical requests with this action_type
    rows = (
        await session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.action_type == row.action_type)
            .order_by(ApprovalRequest.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    matched: list[dict[str, Any]] = []
    for r in rows:
        payload = json.loads(r.proposed_payload or "{}")
        module_type: str | None = None
        agent_owns = False
        if r.action_type == "create_module":
            module_type = payload.get("type")
            agent_owns = True
        elif r.target_kind == "module" and r.target_id:
            mod = await session.get(Module, r.target_id)
            if mod is not None:
                module_type = mod.type
                agent_owns = mod.owner_kind == "agent" and mod.owner_id == r.agent_id
        req = DecisionRequest(
            action_type=r.action_type,
            agent_id=r.agent_id,
            module_type=module_type,
            module_id=r.target_id if r.target_kind == "module" else None,
            page_id=payload.get("page_id"),
            agent_owns_target=agent_owns,
        )
        if _rule_matches(cached, req):
            matched.append(
                {
                    "request_id": r.id,
                    "agent_id": r.agent_id,
                    "status": r.status,
                    "would_have_outcome": cached.outcome,
                    "created_at": r.created_at,
                }
            )
    return {
        "rule_id": rule_id,
        "scanned": len(rows),
        "matched": len(matched),
        "items": matched,
    }


# ---------------------------------------------------------------------------
# Revoke — disable a rule (with optional reverse_decisions)
# ---------------------------------------------------------------------------


# Phase 6: per-action handlers for `reverse_decisions=true`. Each returns
# either ("reverted", detail) on success or ("skipped", reason) when the
# action cannot be safely reversed.

def _decided_by_this_rule(decided_by: str | None, rule_id: str) -> bool:
    """Match the ``decided_by`` audit string for this rule.

    The string is set to ``rule:<id>`` (optionally with `` (retroactive)``
    suffix). We accept either form.
    """
    if not decided_by:
        return False
    return decided_by == f"rule:{rule_id}" or decided_by.startswith(f"rule:{rule_id} ")


async def _reverse_one(
    session: AsyncSession,
    req: ApprovalRequest,
) -> tuple[str, str]:
    """Reverse a single applied decision. Returns ``(status, detail)``.

    Status is ``reverted`` or ``skipped``.
    """
    action = req.action_type
    target_id = req.target_id
    if action == "create_module":
        # Soft-delete the module that was created.
        if not target_id:
            return ("skipped", "no target_id")
        mod = await session.get(Module, target_id)
        if mod is None:
            return ("skipped", "module not found")
        if mod.deleted_at is not None:
            return ("skipped", "already deleted")
        mod.deleted_at = utcnow_iso()
        mod.version += 1
        mod.last_updated_by = "system:rule_revoked"
        return ("reverted", "module soft-deleted")
    if action == "delete_module":
        # Undelete: clear deleted_at.
        if not target_id:
            return ("skipped", "no target_id")
        mod = await session.get(Module, target_id)
        if mod is None:
            return ("skipped", "module not found")
        if mod.deleted_at is None:
            return ("skipped", "not deleted")
        mod.deleted_at = None
        mod.version += 1
        mod.last_updated_by = "system:rule_revoked"
        return ("reverted", "module undeleted")
    if action in {"update_module_data", "update_module_config", "update_module_meta"}:
        return ("skipped", "cannot auto-revert update")
    if action == "create_page":
        if not target_id:
            return ("skipped", "no target_id")
        page = await session.get(Page, target_id)
        if page is None:
            return ("skipped", "page not found")
        if page.kind == "home":
            return ("skipped", "cannot revoke home page")
        if page.deleted_at is not None:
            return ("skipped", "already deleted")
        page.deleted_at = utcnow_iso()
        return ("reverted", "page soft-deleted")
    if action == "delete_page":
        if not target_id:
            return ("skipped", "no target_id")
        page = await session.get(Page, target_id)
        if page is None:
            return ("skipped", "page not found")
        if page.deleted_at is None:
            return ("skipped", "not deleted")
        page.deleted_at = None
        return ("reverted", "page undeleted")
    if action == "fire_action_button":
        return ("skipped", "cannot reverse executed actions")
    return ("skipped", f"unsupported action_type {action}")


@router.post("/{rule_id}/revoke")
async def revoke_rule(
    rule_id: str,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
    reverse_decisions: bool = False,
) -> dict:
    row = await session.get(ApprovalRule, rule_id)
    if row is None:
        raise not_found("approval_rule.not_found", rule_id)
    row.enabled = 0
    await session.flush()
    bump_rules_version()

    reversed_count = 0
    skipped_count = 0
    details: list[dict[str, str]] = []

    if reverse_decisions:
        # Scan the last 24h of auto-approved requests that were decided by
        # this rule. We look at ``applied`` state — the rule could have led
        # to ``applied`` or ``denied``; only ``applied`` rows represent
        # downstream mutations we might want to roll back.
        cutoff_iso = iso_millis(datetime.now(UTC) - timedelta(hours=24))
        stmt = (
            select(ApprovalRequest)
            .where(
                ApprovalRequest.status == "applied",
                ApprovalRequest.decided_at >= cutoff_iso,
            )
            .order_by(ApprovalRequest.decided_at.desc())
        )
        candidates = (await session.execute(stmt)).scalars().all()
        for req in candidates:
            if not _decided_by_this_rule(req.decided_by, rule_id):
                continue
            status, detail = await _reverse_one(session, req)
            entry = {
                "request_id": req.id,
                "action_type": req.action_type,
                "target_id": req.target_id or "",
                "status": status,
                "detail": detail,
            }
            details.append(entry)
            if status == "reverted":
                reversed_count += 1
                # Audit each individual reversal so the activity log lights
                # up with what happened.
                await write_event(
                    session,
                    actor_kind="user",
                    actor_id=user.name,
                    action_type="revoke_decision_reverse",
                    target_kind=req.target_kind,
                    target_id=req.target_id,
                    outcome="applied",
                    payload_summary={
                        "rule_id": rule_id,
                        "request_id": req.id,
                        "action_type": req.action_type,
                        "detail": detail,
                    },
                    request_id=req.id,
                    rule_id=rule_id,
                )
            else:
                skipped_count += 1
        await session.flush()

    await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type="revoke_approval_rule",
        target_kind="approval_rule",
        target_id=row.id,
        outcome="applied",
        payload_summary={
            "reverse_decisions": reverse_decisions,
            "reversed_count": reversed_count,
            "skipped_count": skipped_count,
        },
        rule_id=row.id,
    )
    return {
        "rule": _to_out(row).model_dump(),
        # Legacy field for back-compat with existing UI.
        "reversed": reversed_count,
        "reversed_count": reversed_count,
        "skipped_count": skipped_count,
        "details": details,
    }
