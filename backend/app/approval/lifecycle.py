"""State machine for ``approval_requests.status`` (PLAN §7.5).

Allowed transitions::

    created ─► pending ─► approved ─► applied
                       │           ├─► application_failed
                       │           ├─► executed              (fire_action_button)
                       │           └─► execution_failed      (fire_action_button)
                       ├─► denied
                       ├─► superseded
                       └─► expired

Anything else raises :class:`InvalidTransition`. Callers must compose this
with an activity_log write (see services/audit.write_event).
"""

from __future__ import annotations

import json
from typing import Any

from ..models import ApprovalRequest, utcnow_iso


class InvalidTransition(Exception):
    """Raised when a status change isn't legal for the current status."""

    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(f"Invalid transition: {from_status} -> {to_status}")
        self.from_status = from_status
        self.to_status = to_status


# Map of legal from_status -> set of legal to_status
_ALLOWED: dict[str, set[str]] = {
    "pending": {"approved", "denied", "superseded", "expired"},
    "approved": {"applied", "application_failed", "denied", "superseded"},
    # `applied` is mostly terminal but fire_action requests then move to
    # `executed` / `execution_failed`. We model those as same-state markers
    # on `executed_at` / `execution_result`; the status itself stays
    # `applied` so external observers can simply check ``executed_at``.
    "applied": set(),
    "denied": set(),
    "application_failed": set(),
    "superseded": set(),
    "expired": set(),
}


def _check(from_status: str, to_status: str) -> None:
    allowed = _ALLOWED.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransition(from_status, to_status)


def mark_approved(
    request: ApprovalRequest,
    *,
    decided_by: str,
    decision_reason: str | None = None,
) -> None:
    _check(request.status, "approved")
    request.status = "approved"
    request.decided_at = utcnow_iso()
    request.decided_by = decided_by
    if decision_reason is not None:
        request.decision_reason = decision_reason


def mark_denied(
    request: ApprovalRequest,
    *,
    decided_by: str,
    decision_reason: str | None = None,
) -> None:
    _check(request.status, "denied")
    request.status = "denied"
    request.decided_at = utcnow_iso()
    request.decided_by = decided_by
    if decision_reason is not None:
        request.decision_reason = decision_reason


def mark_applied(request: ApprovalRequest) -> None:
    _check(request.status, "applied")
    request.status = "applied"
    request.applied_at = utcnow_iso()


def mark_application_failed(
    request: ApprovalRequest,
    *,
    reason: str,
) -> None:
    _check(request.status, "application_failed")
    request.status = "application_failed"
    request.applied_at = utcnow_iso()
    # We don't have a dedicated error column on approval_requests; record into
    # decision_reason so the queue UI can surface it.
    request.decision_reason = (
        f"{request.decision_reason}; apply_error={reason}"
        if request.decision_reason
        else f"apply_error={reason}"
    )


def mark_superseded(request: ApprovalRequest, *, reason: str | None = None) -> None:
    _check(request.status, "superseded")
    request.status = "superseded"
    request.decided_at = utcnow_iso()
    request.decided_by = "system:superseded"
    if reason is not None:
        request.decision_reason = reason


def mark_expired(request: ApprovalRequest, *, reason: str = "ttl") -> None:
    _check(request.status, "expired")
    request.status = "expired"
    request.decided_at = utcnow_iso()
    request.decided_by = "system:expired"
    request.decision_reason = reason


def mark_executed(
    request: ApprovalRequest,
    *,
    result: dict[str, Any] | None = None,
) -> None:
    """Record successful execution of a fire_action_button request.

    Status stays ``applied``; we set ``executed_at`` and ``execution_result``.
    Caller should have already called :func:`mark_applied` before this.
    """
    if request.status != "applied":
        raise InvalidTransition(request.status, "executed")
    request.executed_at = utcnow_iso()
    if result is not None:
        request.execution_result = json.dumps(result, separators=(",", ":"), default=str)


def mark_execution_failed(
    request: ApprovalRequest,
    *,
    result: dict[str, Any] | None = None,
) -> None:
    """Mark a fire_action_button as approved + applied + execution_failed.

    The status flips to ``application_failed`` per PLAN §7.4 (action button
    distinct fields), with ``execution_result`` capturing the failure body.
    """
    # Allow from applied (the synchronous path applied first, then failed
    # during webhook execution).
    if request.status != "applied":
        raise InvalidTransition(request.status, "execution_failed")
    request.executed_at = utcnow_iso()
    if result is not None:
        request.execution_result = json.dumps(result, separators=(",", ":"), default=str)
    # We don't mutate the status because the PLAN distinguishes
    # `executed | execution_failed` as sub-states under `applied`. The
    # `execution_result.ok` field tells the UI which it is.


__all__ = [
    "InvalidTransition",
    "mark_approved",
    "mark_denied",
    "mark_applied",
    "mark_application_failed",
    "mark_executed",
    "mark_execution_failed",
    "mark_superseded",
    "mark_expired",
]
