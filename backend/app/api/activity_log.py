"""Read-only ``/api/v1/activity-log`` admin endpoints.

Search (``q``) uses the SQLite FTS5 index on ``activity_log_fts`` created by
migration ``0002_activity_fts``. Results are ordered by ``bm25(...)`` (lower
is more relevant). All other filters (``kind``, ``actor``, dates, target)
apply via plain SQL on the ``activity_log`` row joined by id.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import CurrentUser, require_session
from ..db import read_session
from ..errors import not_found
from ..models import ActivityLog, AuditBlob

router = APIRouter(prefix="/api/v1/activity-log", tags=["activity-log"])


def _to_out(row: Any) -> dict[str, Any]:
    """Translate an ``ActivityLog`` ORM row or a raw SQLAlchemy row (from the
    FTS join) into the output dict. Both expose the same attribute names."""
    payload = json.loads(row.payload_summary) if row.payload_summary else None
    return {
        "id": row.id,
        "timestamp": row.timestamp,
        "actor_kind": row.actor_kind,
        "actor_id": row.actor_id,
        "action_type": row.action_type,
        "target_kind": row.target_kind,
        "target_id": row.target_id,
        "payload_summary": payload,
        "outcome": row.outcome,
        "request_id": row.request_id,
        "rule_id": row.rule_id,
        "error_detail": row.error_detail,
    }


def _split_kinds(kind: str | None) -> list[str]:
    """Split a CSV query param (``kind``, ``outcome``) into clean tokens."""
    if not kind:
        return []
    return [k.strip() for k in kind.split(",") if k.strip()]


def _parse_cursor_id(cursor: str | None) -> int | None:
    """Parse a numeric pagination cursor; return ``None`` when absent/invalid."""
    if not cursor:
        return None
    try:
        return int(cursor)
    except ValueError:
        return None


# Sanitize the user-supplied search query: FTS5 has a fragile syntax (quotes,
# parens, NEAR/MATCH operators). For a homelab admin we accept whitespace +
# alphanumerics + underscores/hyphens, split on spaces, wrap each term in
# double-quotes, and join with implicit AND. Pathological inputs degrade to
# an empty query string.
_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]+")


def _build_fts_match(q: str) -> str:
    tokens = _FTS_TOKEN_RE.findall(q)
    if not tokens:
        return ""
    # Quote each token to disable FTS5 operators inside it; suffix '*' to
    # allow prefix matching, which makes searches like 'mod_01H' useful.
    quoted = [f'"{t}"*' for t in tokens]
    return " ".join(quoted)


@router.get("")
async def list_activity(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
    kind: str | None = None,  # CSV of action_type values
    outcome: str | None = None,  # CSV of outcome values
    actor: str | None = None,
    target_kind: str | None = None,
    target_id: str | None = None,
    q: str | None = None,
    after: str | None = None,
    before: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    fts_match = _build_fts_match(q) if q else ""

    if fts_match:
        # FTS5 path: join activity_log onto activity_log_fts. bm25 sorts
        # by relevance (lower is better). We then secondary-sort by id desc
        # for stable cursor pagination among equally-ranked rows.
        clauses = ["activity_log_fts MATCH :match"]
        params: dict[str, Any] = {"match": fts_match}
        kinds = _split_kinds(kind)
        if kinds:
            placeholders = ",".join(f":kind{i}" for i in range(len(kinds)))
            clauses.append(f"a.action_type IN ({placeholders})")
            for i, k in enumerate(kinds):
                params[f"kind{i}"] = k
        outcomes = _split_kinds(outcome)
        if outcomes:
            placeholders = ",".join(f":outcome{i}" for i in range(len(outcomes)))
            clauses.append(f"a.outcome IN ({placeholders})")
            for i, o in enumerate(outcomes):
                params[f"outcome{i}"] = o
        if actor:
            clauses.append("a.actor_id = :actor")
            params["actor"] = actor
        if target_kind:
            clauses.append("a.target_kind = :target_kind")
            params["target_kind"] = target_kind
        if target_id:
            clauses.append("a.target_id = :target_id")
            params["target_id"] = target_id
        if after:
            clauses.append("a.timestamp >= :after")
            params["after"] = after
        if before:
            clauses.append("a.timestamp <= :before")
            params["before"] = before
        cursor_id = _parse_cursor_id(cursor)
        if cursor_id is not None:
            params["cursor"] = cursor_id
            clauses.append("a.id < :cursor")
        params["lim"] = limit + 1
        where = " AND ".join(clauses)
        sql = (
            "SELECT a.id, a.timestamp, a.actor_kind, a.actor_id, a.action_type, "
            "       a.target_kind, a.target_id, a.payload_summary, a.outcome, "
            "       a.request_id, a.rule_id, a.error_detail "
            "FROM activity_log a "
            "JOIN activity_log_fts f ON f.rowid = a.id "
            f"WHERE {where} "
            "ORDER BY bm25(activity_log_fts), a.id DESC "
            "LIMIT :lim"
        )
        rows = (await session.execute(sql_text(sql), params)).all()
        next_cursor = str(rows[limit].id) if len(rows) > limit else None
        items = [_to_out(r) for r in rows[:limit]]
        return {"items": items, "next_cursor": next_cursor}

    # Non-search path: ORM SELECT with filters, sorted by id desc.
    stmt = select(ActivityLog)
    kinds = _split_kinds(kind)
    if kinds:
        stmt = stmt.where(ActivityLog.action_type.in_(kinds))
    outcomes = _split_kinds(outcome)
    if outcomes:
        stmt = stmt.where(ActivityLog.outcome.in_(outcomes))
    if actor:
        stmt = stmt.where(ActivityLog.actor_id == actor)
    if target_kind:
        stmt = stmt.where(ActivityLog.target_kind == target_kind)
    if target_id:
        stmt = stmt.where(ActivityLog.target_id == target_id)
    if after:
        stmt = stmt.where(ActivityLog.timestamp >= after)
    if before:
        stmt = stmt.where(ActivityLog.timestamp <= before)
    cursor_id = _parse_cursor_id(cursor)
    if cursor_id is not None:
        # Cursor is the numeric id; we walk backwards from the most recent.
        stmt = stmt.where(ActivityLog.id < cursor_id)
    stmt = stmt.order_by(ActivityLog.id.desc()).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    next_cursor = str(rows[limit].id) if len(rows) > limit else None
    items = [_to_out(r) for r in rows[:limit]]
    return {"items": items, "next_cursor": next_cursor}


@router.get("/{activity_id}")
async def get_activity(
    activity_id: int,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> dict:
    row = await session.get(ActivityLog, activity_id)
    if row is None:
        raise not_found("activity.not_found", str(activity_id))
    out = _to_out(row)
    # If payload_summary spilled to a blob, hydrate the full body.
    payload = out.get("payload_summary")
    if isinstance(payload, dict) and payload.get("_blob_sha256"):
        blob = await session.get(AuditBlob, payload["_blob_sha256"])
        if blob is not None:
            try:
                out["audit_blob"] = json.loads(blob.body)
            except json.JSONDecodeError:
                out["audit_blob"] = {"_raw": blob.body[:65536]}
    return out
