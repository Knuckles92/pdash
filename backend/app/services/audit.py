"""Audit log writes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..events.publish import publish_after_commit
from ..models import ActivityLog, AuditBlob, utcnow_iso


async def write_event(
    session: AsyncSession,
    *,
    actor_kind: str,
    actor_id: str | None,
    action_type: str,
    target_kind: str | None,
    target_id: str | None,
    outcome: str,
    payload_summary: dict[str, Any] | None = None,
    request_id: str | None = None,
    rule_id: str | None = None,
    error_detail: str | None = None,
) -> ActivityLog:
    """Insert one activity_log row.

    If payload_summary exceeds the configured threshold, the full payload is
    spilled to `audit_blobs` and the summary is replaced by
    `{"_blob_sha256": "...", "_truncated": true}`.
    """
    settings = get_settings()
    summary_json: str | None = None
    if payload_summary is not None:
        encoded = json.dumps(payload_summary, separators=(",", ":"), default=str)
        if len(encoded.encode("utf-8")) > settings.audit_blob_threshold_bytes:
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            # Insert blob if not present.
            existing = await session.get(AuditBlob, digest)
            if existing is None:
                session.add(
                    AuditBlob(sha256=digest, body=encoded, created_at=utcnow_iso())
                )
            summary_json = json.dumps(
                {"_blob_sha256": digest, "_truncated": True}, separators=(",", ":")
            )
        else:
            summary_json = encoded

    row = ActivityLog(
        timestamp=utcnow_iso(),
        actor_kind=actor_kind,
        actor_id=actor_id,
        action_type=action_type,
        target_kind=target_kind,
        target_id=target_id,
        payload_summary=summary_json,
        outcome=outcome,
        request_id=request_id,
        rule_id=rule_id,
        error_detail=error_detail,
    )
    session.add(row)
    await session.flush()

    # Phase 5: publish to the `activity` channel for live tail / "N new" pill.
    publish_after_commit(
        session,
        "activity",
        "activity_appended",
        {
            "id": row.id,
            "timestamp": row.timestamp,
            "actor_kind": actor_kind,
            "actor_id": actor_id,
            "action_type": action_type,
            "target_kind": target_kind,
            "target_id": target_id,
            "outcome": outcome,
            "request_id": request_id,
            "rule_id": rule_id,
        },
    )
    return row
