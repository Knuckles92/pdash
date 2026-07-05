"""High-level orchestration: from an incoming proposal to a decision + apply.

This is the function the internal endpoints call. It:

1. Builds an ``ApprovalRequest`` row from the proposed payload + decision
   inputs (action_type, target_kind/id, agent_owns_target).
2. Calls :func:`engine.decide` to get the engine's verdict.
3. Persists the request with the appropriate status:
   - ``auto_approve`` → write row as ``approved`` and immediately apply.
   - ``deny``        → write row as ``denied``.
   - ``prompt``      → write row as ``pending`` with an ``expires_at``.
4. Writes activity_log entries on every state transition.
5. Returns an :class:`OrchestratedResult` describing what happened.

All of this runs inside the caller's transaction; the caller is responsible
for the surrounding ``BEGIN IMMEDIATE`` boundary (FastAPI's ``get_session``
dep already does this).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ..events.publish import publish_after_commit
from ..ids import new_id
from ..models import ApprovalRequest, ApprovalRule, utcnow_iso
from ..services.agent_registration import sync_registration_denied_from_approval
from ..services.audit import write_event
from . import lifecycle
from .apply import ApplyError, ApplyResult, apply_request
from .engine import Decision, DecisionRequest, decide
from .expiry import compute_expires_at

ResultStatus = Literal["applied", "pending", "denied", "application_failed"]


@dataclass
class OrchestratedResult:
    status: ResultStatus
    request: ApprovalRequest
    decision: Decision
    audit_id: int | None
    apply_result: ApplyResult | None = None
    apply_error: ApplyError | None = None


def _summary_payload(
    action_type: str,
    payload: dict[str, Any],
    *,
    decision: Decision,
    rationale: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "action_type": action_type,
        "decision": decision.status,
    }
    if decision.rule_id:
        base["rule_id"] = decision.rule_id
    if rationale:
        base["rationale"] = rationale
    # Trim payload to a small summary so we don't write the full thing inline
    # unless ``write_event`` spills to a blob (32KB threshold).
    base["payload_keys"] = sorted(list(payload.keys()))[:20]
    if extra:
        base.update(extra)
    return base


async def _bump_rule_application_count(
    session: AsyncSession, rule_id: str | None
) -> None:
    """Increment a rule's application_count + last_applied_at, if it exists."""
    if not rule_id:
        return
    rule = await session.get(ApprovalRule, rule_id)
    if rule is not None:
        rule.application_count = (rule.application_count or 0) + 1
        rule.last_applied_at = utcnow_iso()
        await session.flush()


def _actor_label(agent_id: str | None) -> str:
    return f"agent:{agent_id}" if agent_id else "bootstrap"


def _publish_approval_decided(
    session: AsyncSession,
    request: ApprovalRequest,
    *,
    agent_id: str | None,
    action_type: str,
    outcome: str,
    rule_id: str | None,
    applied_at: str | None = None,
) -> None:
    """Publish the ``approval_decided`` event shared by the approve/deny paths."""
    payload: dict[str, Any] = {
        "request_id": request.id,
        "agent_id": agent_id,
        "action_type": action_type,
        "target_kind": request.target_kind,
        "target_id": request.target_id,
        "outcome": outcome,
        "rule_id": rule_id,
        "decided_at": request.decided_at,
        "decision_reason": request.decision_reason,
    }
    if applied_at is not None:
        payload["applied_at"] = applied_at
    publish_after_commit(session, "approvals", "approval_decided", payload)


async def submit_request(
    session: AsyncSession,
    *,
    agent_id: str | None,
    action_type: str,
    target_kind: str | None,
    target_id: str | None,
    proposed_payload: dict[str, Any],
    module_type: str | None = None,
    page_id: str | None = None,
    agent_owns_target: bool = False,
    idempotency_key: str | None = None,
    rationale: str | None = None,
) -> OrchestratedResult:
    """Run a proposal through the engine. Persist + apply atomically.

    The caller has already validated/authn'd the agent. ``proposed_payload``
    is the JSON body that ``apply_request`` will consume on the approved
    branch — so it must include any provisional ID (for create_*) that the
    caller minted.
    """
    decision_req = DecisionRequest(
        action_type=action_type,
        agent_id=agent_id,
        module_type=module_type,
        module_id=target_id if target_kind == "module" else None,
        page_id=page_id,
        agent_owns_target=agent_owns_target,
    )
    decision = await decide(session, decision_req)

    request_id = new_id("apr")
    now = utcnow_iso()
    request = ApprovalRequest(
        id=request_id,
        agent_id=agent_id,
        action_type=action_type,
        target_kind=target_kind,
        target_id=target_id,
        proposed_payload=json.dumps(proposed_payload, separators=(",", ":"), default=str),
        idempotency_key=idempotency_key,
        status="pending",
        created_at=now,
        expires_at=compute_expires_at() if decision.status == "prompt" else None,
        # Rationale lives in decision_reason for pending rows; lifecycle helpers
        # will overwrite when the admin decides.
        decision_reason=rationale if decision.status == "prompt" else None,
    )
    session.add(request)
    await session.flush()

    via_rule = decision.rule_id is not None

    # ------------------------------------------------------------------
    # Auto-approve fast path
    # ------------------------------------------------------------------
    if decision.status == "auto_approve":
        lifecycle.mark_approved(
            request,
            decided_by=f"rule:{decision.rule_id}" if decision.rule_id else "system:auto",
            decision_reason=rationale,
        )
        try:
            result = await apply_request(
                session, request, actor=_actor_label(agent_id),
            )
        except ApplyError as exc:
            lifecycle.mark_application_failed(request, reason=str(exc))
            log = await write_event(
                session,
                actor_kind="rule" if via_rule else "system",
                actor_id=decision.rule_id or "auto",
                action_type=action_type,
                target_kind=request.target_kind,
                target_id=request.target_id,
                outcome="error",
                payload_summary={
                    "decision": "auto_approve",
                    "apply_error": str(exc),
                    "rule_id": decision.rule_id,
                },
                request_id=request_id,
                rule_id=decision.rule_id,
                error_detail=str(exc),
            )
            return OrchestratedResult(
                status="application_failed",
                request=request,
                decision=decision,
                audit_id=log.id,
                apply_error=exc,
            )
        log = await write_event(
            session,
            actor_kind="rule" if via_rule else "system",
            actor_id=decision.rule_id or "auto",
            action_type=action_type,
            target_kind=request.target_kind,
            target_id=request.target_id,
            outcome="auto_approved",
            payload_summary=_summary_payload(
                action_type, proposed_payload, decision=decision,
                rationale=rationale,
                extra={"applied_at": request.applied_at},
            ),
            request_id=request_id,
            rule_id=decision.rule_id,
        )
        # Bump rule application_count if matched
        await _bump_rule_application_count(session, decision.rule_id)
        # Phase 5: notify subscribers that this auto-approved request is decided.
        # The underlying state change (module/page) is published by apply.py.
        _publish_approval_decided(
            session,
            request,
            agent_id=agent_id,
            action_type=action_type,
            outcome="applied",
            rule_id=decision.rule_id,
            applied_at=request.applied_at,
        )
        return OrchestratedResult(
            status="applied",
            request=request,
            decision=decision,
            audit_id=log.id,
            apply_result=result,
        )

    # ------------------------------------------------------------------
    # Deny fast path
    # ------------------------------------------------------------------
    if decision.status == "deny":
        lifecycle.mark_denied(
            request,
            decided_by=f"rule:{decision.rule_id}" if decision.rule_id else "system:deny",
            decision_reason=rationale or "denied by rule",
        )
        await sync_registration_denied_from_approval(
            session,
            request,
            decided_by=f"rule:{decision.rule_id}" if decision.rule_id else "system:deny",
            reason=rationale or "denied by rule",
        )
        log = await write_event(
            session,
            actor_kind="rule" if via_rule else "system",
            actor_id=decision.rule_id or "deny",
            action_type=action_type,
            target_kind=target_kind,
            target_id=target_id,
            outcome="denied",
            payload_summary=_summary_payload(
                action_type, proposed_payload, decision=decision, rationale=rationale,
            ),
            request_id=request_id,
            rule_id=decision.rule_id,
        )
        await _bump_rule_application_count(session, decision.rule_id)
        _publish_approval_decided(
            session,
            request,
            agent_id=agent_id,
            action_type=action_type,
            outcome="denied",
            rule_id=decision.rule_id,
        )
        return OrchestratedResult(
            status="denied",
            request=request,
            decision=decision,
            audit_id=log.id,
        )

    # ------------------------------------------------------------------
    # Pending
    # ------------------------------------------------------------------
    log = await write_event(
        session,
        actor_kind="agent" if agent_id else "system",
        actor_id=agent_id or "bootstrap",
        action_type=action_type,
        target_kind=target_kind,
        target_id=target_id,
        outcome="queued",
        payload_summary=_summary_payload(
            action_type, proposed_payload, decision=decision, rationale=rationale,
        ),
        request_id=request_id,
    )
    publish_after_commit(
        session,
        "approvals",
        "approval_pending",
        {
            "request_id": request.id,
            "agent_id": agent_id,
            "action_type": action_type,
            "target_kind": target_kind,
            "target_id": target_id,
            "module_type": module_type,
            "page_id": page_id,
            "created_at": request.created_at,
            "expires_at": request.expires_at,
        },
    )
    return OrchestratedResult(
        status="pending",
        request=request,
        decision=decision,
        audit_id=log.id,
    )


__all__ = ["OrchestratedResult", "submit_request"]
