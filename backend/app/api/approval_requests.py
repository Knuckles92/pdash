"""Admin endpoints for ``/api/v1/approval-requests/*``."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..approval import bump_rules_version, lifecycle
from ..approval.apply import ApplyError, apply_request
from ..approval.engine import DecisionRequest, decide
from ..approval.preview import (
    build_action_preview,
    build_dashboard_preview,
    build_file_preview,
    build_registration_preview,
)
from ..auth.deps import CurrentUser, require_csrf, require_session
from ..db import get_session, read_session
from ..errors import bad_request, not_found
from ..events.publish import publish_after_commit
from ..ids import new_id
from ..models import AgentRegistrationRequest, ApprovalRequest, ApprovalRule, Module, utcnow_iso
from ..schemas import (
    ApprovalRequestDetailOut,
    ApprovalRequestListOut,
    ApprovalRequestOut,
    ApprovalRuleDraft,
    ApproveIn,
    BulkDecideIn,
    BulkDecideOut,
    BulkDecisionResult,
    DenyIn,
)
from ..services.agent_registration import sync_registration_denied_from_approval
from ..services.audit import write_event

router = APIRouter(prefix="/api/v1/approval-requests", tags=["approval-requests"])


def _to_out(row: ApprovalRequest) -> ApprovalRequestOut:
    return ApprovalRequestOut(
        id=row.id,
        agent_id=row.agent_id,
        action_type=row.action_type,
        target_kind=row.target_kind,
        target_id=row.target_id,
        proposed_payload=json.loads(row.proposed_payload or "{}"),
        idempotency_key=row.idempotency_key,
        status=row.status,
        created_at=row.created_at,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
        decision_reason=row.decision_reason,
        applied_at=row.applied_at,
        executed_at=row.executed_at,
        execution_result=json.loads(row.execution_result) if row.execution_result else None,
        expires_at=row.expires_at,
    )


def _shallow_diff(current: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    """Return a per-key diff for update_module_data / _config payloads."""
    keys = sorted(set(current.keys()) | set(proposed.keys()))
    diff: dict[str, Any] = {}
    for k in keys:
        before = current.get(k)
        after = proposed.get(k)
        if before != after:
            diff[k] = {"before": before, "after": after}
    return diff


def _publish_approval_decided(
    session: AsyncSession,
    row: ApprovalRequest,
    *,
    outcome: str,
    include_applied_at: bool = False,
) -> None:
    """Publish the ``approval_decided`` event for a just-decided request.

    The payload is shared by the approve/deny and bulk-decide paths; only
    ``outcome`` and whether ``applied_at`` is included differ between them.
    """
    payload: dict[str, Any] = {
        "request_id": row.id,
        "agent_id": row.agent_id,
        "action_type": row.action_type,
        "target_kind": row.target_kind,
        "target_id": row.target_id,
        "outcome": outcome,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
    }
    if include_applied_at:
        payload["applied_at"] = row.applied_at
    payload["decision_reason"] = row.decision_reason
    publish_after_commit(session, "approvals", "approval_decided", payload)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=ApprovalRequestListOut)
async def list_requests(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
    status: str | None = None,
    agent_id: str | None = None,
    action_type: str | None = None,
    page_id: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> ApprovalRequestListOut:
    stmt = select(ApprovalRequest)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    if agent_id:
        stmt = stmt.where(ApprovalRequest.agent_id == agent_id)
    if action_type:
        stmt = stmt.where(ApprovalRequest.action_type == action_type)
    if page_id:
        # match against target_id when target_kind=page, or via module's page_id
        # Phase 3: simple match on target_kind=page; module variants come Phase 4.
        stmt = stmt.where(
            (ApprovalRequest.target_kind == "page")
            & (ApprovalRequest.target_id == page_id)
        )
    if created_after:
        stmt = stmt.where(ApprovalRequest.created_at >= created_after)
    if created_before:
        stmt = stmt.where(ApprovalRequest.created_at <= created_before)
    if cursor:
        stmt = stmt.where(ApprovalRequest.id > cursor)
    stmt = stmt.order_by(ApprovalRequest.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    next_cursor = rows[limit].id if len(rows) > limit else None
    items = [_to_out(r) for r in rows[:limit]]

    total_pending: int | None = None
    if not status:
        total_pending = (
            await session.scalar(
                select(func.count()).select_from(ApprovalRequest).where(
                    ApprovalRequest.status == "pending"
                )
            )
        ) or 0
    return ApprovalRequestListOut(
        items=items, next_cursor=next_cursor, total_pending=total_pending
    )


# ---------------------------------------------------------------------------
# Get one
# ---------------------------------------------------------------------------


@router.get("/{request_id}", response_model=ApprovalRequestDetailOut)
async def get_request(
    request_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> ApprovalRequestDetailOut:
    row = await session.get(ApprovalRequest, request_id)
    if row is None:
        raise not_found("approval_request.not_found", request_id)
    out = _to_out(row)
    diff_preview: dict[str, Any] | None = None
    if row.action_type in ("update_module_data", "update_module_config") and row.target_kind == "module":
        mod = await session.get(Module, row.target_id)
        if mod is not None:
            payload = json.loads(row.proposed_payload or "{}")
            patch = payload.get("patch", {})
            if "data" in patch:
                current = json.loads(mod.data or "{}")
                diff_preview = {"data": _shallow_diff(current, patch["data"])}
            elif "config" in patch:
                current = json.loads(mod.config or "{}")
                diff_preview = {"config": _shallow_diff(current, patch["config"])}
    dashboard_preview = await build_dashboard_preview(session, row)
    action_preview = await build_action_preview(session, row)
    file_preview = await build_file_preview(session, row)
    registration_preview = await build_registration_preview(session, row)
    return ApprovalRequestDetailOut(
        **out.model_dump(),
        diff_preview=diff_preview,
        dashboard_preview=dashboard_preview,
        action_preview=action_preview,
        file_preview=file_preview,
        registration_preview=registration_preview,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _agent_owns_module(
    session: AsyncSession, *, agent_id: str, target_kind: str | None, target_id: str | None
) -> bool:
    if target_kind != "module" or not target_id:
        return False
    mod = await session.get(Module, target_id)
    if mod is None:
        return False
    return mod.owner_kind == "agent" and mod.owner_id == agent_id


async def _create_rule_from_draft(
    session: AsyncSession,
    *,
    draft: ApprovalRuleDraft,
    created_by: str,
) -> ApprovalRule:
    row = ApprovalRule(
        id=new_id("rule"),
        agent_id=draft.agent_id,
        action_type=draft.action_type,
        module_type=draft.module_type,
        module_id=draft.module_id,
        page_id=draft.page_id,
        owner_scope=draft.owner_scope,
        outcome=draft.outcome,
        priority=draft.priority,
        is_builtin=0,
        enabled=1 if draft.enabled else 0,
        notes=draft.notes,
        created_at=utcnow_iso(),
        created_by=created_by,
        application_count=0,
    )
    session.add(row)
    await session.flush()
    bump_rules_version()
    return row


async def _apply_to_pending(
    session: AsyncSession, *, action_type: str, actor: str
) -> int:
    """Sweep all pending requests matching the new rule's action_type through
    the engine. Returns the number of newly-applied or denied requests.
    """
    rows = (
        await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == "pending",
                ApprovalRequest.action_type == action_type,
            )
        )
    ).scalars().all()
    affected = 0
    for request in rows:
        # Compute ownership against current module state.
        agent_owns_target = await _agent_owns_module(
            session, agent_id=request.agent_id or "",
            target_kind=request.target_kind, target_id=request.target_id,
        )
        payload = json.loads(request.proposed_payload or "{}")
        module_type: str | None = None
        if request.action_type == "create_module":
            module_type = payload.get("type")
        elif request.target_kind == "module" and request.target_id:
            mod = await session.get(Module, request.target_id)
            if mod is not None:
                module_type = mod.type
        decision = await decide(
            session,
            DecisionRequest(
                action_type=request.action_type,
                agent_id=request.agent_id,
                module_type=module_type,
                module_id=request.target_id if request.target_kind == "module" else None,
                page_id=payload.get("page_id"),
                agent_owns_target=agent_owns_target,
            ),
        )
        if decision.status == "auto_approve":
            lifecycle.mark_approved(
                request,
                decided_by=f"rule:{decision.rule_id} (retroactive)",
                decision_reason="apply_to_pending sweep",
            )
            try:
                await apply_request(session, request, actor=actor)
                await write_event(
                    session,
                    actor_kind="rule",
                    actor_id=decision.rule_id,
                    action_type=request.action_type,
                    target_kind=request.target_kind,
                    target_id=request.target_id,
                    outcome="auto_approved",
                    payload_summary={"retroactive": True, "rule_id": decision.rule_id},
                    request_id=request.id,
                    rule_id=decision.rule_id,
                )
                affected += 1
            except ApplyError as exc:
                lifecycle.mark_application_failed(request, reason=str(exc))
                await write_event(
                    session,
                    actor_kind="rule",
                    actor_id=decision.rule_id,
                    action_type=request.action_type,
                    target_kind=request.target_kind,
                    target_id=request.target_id,
                    outcome="error",
                    error_detail=str(exc),
                    request_id=request.id,
                    rule_id=decision.rule_id,
                )
        elif decision.status == "deny":
            lifecycle.mark_denied(
                request,
                decided_by=f"rule:{decision.rule_id} (retroactive)",
                decision_reason="apply_to_pending sweep",
            )
            await sync_registration_denied_from_approval(
                session,
                request,
                decided_by=f"rule:{decision.rule_id} (retroactive)",
                reason="apply_to_pending sweep",
            )
            await write_event(
                session,
                actor_kind="rule",
                actor_id=decision.rule_id,
                action_type=request.action_type,
                target_kind=request.target_kind,
                target_id=request.target_id,
                outcome="denied",
                payload_summary={"retroactive": True, "rule_id": decision.rule_id},
                request_id=request.id,
                rule_id=decision.rule_id,
            )
            affected += 1
    return affected


# ---------------------------------------------------------------------------
# approve / deny
# ---------------------------------------------------------------------------


@router.post("/{request_id}/approve")
async def approve_request(
    request_id: str,
    body: ApproveIn,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    row = await session.get(ApprovalRequest, request_id)
    if row is None:
        raise not_found("approval_request.not_found", request_id)
    if row.status != "pending":
        raise bad_request(
            "approval_request.not_pending",
            f"Request is in status {row.status!r}, cannot approve",
        )

    # Re-validate at apply time happens inside apply_request.
    if row.action_type == "register_agent" and body.registration is not None:
        payload = json.loads(row.proposed_payload or "{}")
        if body.registration.display_name is not None:
            payload["display_name"] = body.registration.display_name
        if body.registration.description is not None:
            payload["description"] = body.registration.description
        if body.registration.permissions is not None:
            payload["permissions"] = body.registration.permissions
        row.proposed_payload = json.dumps(payload, separators=(",", ":"), default=str)
        await session.flush()

    lifecycle.mark_approved(
        row,
        decided_by=f"admin:{user.name}",
        decision_reason=body.reason,
    )

    apply_error: ApplyError | None = None
    try:
        result = await apply_request(session, row, actor=f"admin:{user.name}")
    except ApplyError as exc:
        apply_error = exc
        lifecycle.mark_application_failed(row, reason=str(exc))
        result = None

    applied_payload: dict[str, Any] | None = None
    if result is not None and result.extra:
        applied_payload = dict(result.extra)

    audit = await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type=row.action_type,
        target_kind=row.target_kind,
        target_id=row.target_id,
        outcome="applied" if apply_error is None else "error",
        payload_summary={
            "from_status": "pending",
            "to_status": row.status,
            "reason": body.reason,
        },
        request_id=row.id,
        error_detail=str(apply_error) if apply_error else None,
    )

    _publish_approval_decided(
        session,
        row,
        outcome="applied" if apply_error is None else "application_failed",
        include_applied_at=True,
    )

    rule_row: ApprovalRule | None = None
    if body.create_rule is not None:
        rule_row = await _create_rule_from_draft(
            session, draft=body.create_rule, created_by=f"admin:{user.name}"
        )
        if body.create_rule.apply_to_pending:
            await _apply_to_pending(
                session, action_type=body.create_rule.action_type,
                actor=f"admin:{user.name}",
            )

    response: dict[str, Any] = {
        "request": _to_out(row).model_dump(),
        "applied": apply_error is None,
        "audit_id": audit.id,
    }
    if applied_payload:
        response["apply_result"] = applied_payload
    if apply_error is not None:
        response["error"] = str(apply_error)
    if rule_row is not None:
        response["rule"] = {
            "id": rule_row.id,
            "agent_id": rule_row.agent_id,
            "action_type": rule_row.action_type,
            "outcome": rule_row.outcome,
        }
    return response


@router.post("/{request_id}/deny")
async def deny_request(
    request_id: str,
    body: DenyIn,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    row = await session.get(ApprovalRequest, request_id)
    if row is None:
        raise not_found("approval_request.not_found", request_id)
    if row.status != "pending":
        raise bad_request(
            "approval_request.not_pending",
            f"Request is in status {row.status!r}, cannot deny",
        )
    lifecycle.mark_denied(
        row,
        decided_by=f"admin:{user.name}",
        decision_reason=body.reason,
    )
    await sync_registration_denied_from_approval(
        session,
        row,
        decided_by=f"admin:{user.name}",
        reason=body.reason,
    )
    audit = await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type=row.action_type,
        target_kind=row.target_kind,
        target_id=row.target_id,
        outcome="denied",
        payload_summary={
            "from_status": "pending",
            "to_status": "denied",
            "reason": body.reason,
        },
        request_id=row.id,
    )
    _publish_approval_decided(session, row, outcome="denied")
    rule_row: ApprovalRule | None = None
    if body.create_rule is not None:
        rule_row = await _create_rule_from_draft(
            session, draft=body.create_rule, created_by=f"admin:{user.name}"
        )
        if body.create_rule.apply_to_pending:
            await _apply_to_pending(
                session, action_type=body.create_rule.action_type,
                actor=f"admin:{user.name}",
            )
    response: dict[str, Any] = {
        "request": _to_out(row).model_dump(),
        "audit_id": audit.id,
    }
    if rule_row is not None:
        response["rule"] = {
            "id": rule_row.id,
            "agent_id": rule_row.agent_id,
            "action_type": rule_row.action_type,
            "outcome": rule_row.outcome,
        }
    return response


# ---------------------------------------------------------------------------
# bulk decide
# ---------------------------------------------------------------------------


@router.post("/bulk-decide", response_model=BulkDecideOut)
async def bulk_decide(
    body: BulkDecideIn,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BulkDecideOut:
    results: list[BulkDecisionResult] = []
    for decision in body.decisions:
        row = await session.get(ApprovalRequest, decision.id)
        if row is None:
            results.append(BulkDecisionResult(id=decision.id, status="not_found", error="not found"))
            continue
        if row.status != "pending":
            results.append(
                BulkDecisionResult(
                    id=decision.id,
                    status=row.status,
                    error=f"already {row.status}",
                )
            )
            continue
        try:
            if decision.decision == "approve":
                lifecycle.mark_approved(
                    row,
                    decided_by=f"admin:{user.name}",
                    decision_reason=decision.reason,
                )
                try:
                    await apply_request(session, row, actor=f"admin:{user.name}")
                    await write_event(
                        session,
                        actor_kind="user",
                        actor_id=user.name,
                        action_type=row.action_type,
                        target_kind=row.target_kind,
                        target_id=row.target_id,
                        outcome="applied",
                        payload_summary={"bulk": True, "to_status": "applied"},
                        request_id=row.id,
                    )
                    _publish_approval_decided(
                        session, row, outcome="applied", include_applied_at=True
                    )
                    results.append(BulkDecisionResult(id=decision.id, status="applied"))
                except ApplyError as exc:
                    lifecycle.mark_application_failed(row, reason=str(exc))
                    await write_event(
                        session,
                        actor_kind="user",
                        actor_id=user.name,
                        action_type=row.action_type,
                        target_kind=row.target_kind,
                        target_id=row.target_id,
                        outcome="error",
                        error_detail=str(exc),
                        request_id=row.id,
                    )
                    results.append(
                        BulkDecisionResult(
                            id=decision.id,
                            status="application_failed",
                            error=str(exc),
                        )
                    )
            else:  # deny
                lifecycle.mark_denied(
                    row,
                    decided_by=f"admin:{user.name}",
                    decision_reason=decision.reason,
                )
                await sync_registration_denied_from_approval(
                    session,
                    row,
                    decided_by=f"admin:{user.name}",
                    reason=decision.reason,
                )
                await write_event(
                    session,
                    actor_kind="user",
                    actor_id=user.name,
                    action_type=row.action_type,
                    target_kind=row.target_kind,
                    target_id=row.target_id,
                    outcome="denied",
                    payload_summary={"bulk": True, "to_status": "denied"},
                    request_id=row.id,
                )
                _publish_approval_decided(session, row, outcome="denied")
                results.append(BulkDecisionResult(id=decision.id, status="denied"))
        except Exception as exc:  # noqa: BLE001
            results.append(
                BulkDecisionResult(
                    id=decision.id, status="error", error=str(exc)
                )
            )
    return BulkDecideOut(results=results)
