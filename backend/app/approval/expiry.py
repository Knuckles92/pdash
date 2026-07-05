"""Sweep stale ``pending`` rows past their ``expires_at`` to ``expired``.

Phase 3 keeps this as an admin-callable function rather than a background
daemon. Phase 6 will add a periodic scheduler.

PLAN §10 P0 item 7: expired is a distinct status from denied — agents can
re-submit and audit-log shows the natural reason.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import ApprovalRequest, utcnow_iso
from ..services.audit import write_event
from ..timefmt import iso_millis
from . import lifecycle


def compute_expires_at() -> str:
    """ISO-8601 UTC timestamp when a new pending row should expire."""
    delta = timedelta(seconds=get_settings().pending_ttl_seconds)
    return iso_millis(datetime.now(UTC) + delta)


async def expire_stale_pending(
    session: AsyncSession, *, now: str | None = None
) -> int:
    """Flip all ``pending`` rows where ``expires_at <= now`` to ``expired``.

    Returns the number of rows expired. Writes an activity_log row per
    transition with ``decided_by='system:expired'``.
    """
    now = now or utcnow_iso()
    rows = (
        await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == "pending",
                ApprovalRequest.expires_at.is_not(None),
                ApprovalRequest.expires_at <= now,
            )
        )
    ).scalars().all()
    count = 0
    for row in rows:
        prev_status = row.status
        lifecycle.mark_expired(row, reason="ttl")
        await write_event(
            session,
            actor_kind="system",
            actor_id="expiry-sweeper",
            action_type=row.action_type,
            target_kind=row.target_kind,
            target_id=row.target_id,
            outcome="denied",
            payload_summary={
                "from_status": prev_status,
                "to_status": "expired",
                "reason": "ttl",
            },
            request_id=row.id,
        )
        count += 1
    await session.flush()
    return count


__all__ = ["compute_expires_at", "expire_stale_pending"]
