"""Action target endpoints."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import CurrentUser, require_csrf, require_session
from ..db import get_session, read_session
from ..errors import bad_request, conflict, not_found
from ..ids import new_id
from ..models import ActionTarget, utcnow_iso
from ..schemas import (
    ActionTargetCreate,
    ActionTargetOut,
    ActionTargetTestResult,
    ActionTargetUpdate,
    CursorPage,
)
from ..services.audit import write_event
from ..services.redact import redact

router = APIRouter(prefix="/api/v1/action-targets", tags=["action-targets"])

ALLOWED_KINDS = {"webhook", "local_script", "mcp_tool", "agent_message"}
ALLOWED_MODES = {"sync", "async"}


def _to_out(row: ActionTarget) -> ActionTargetOut:
    raw_cfg = json.loads(row.config or "{}")
    return ActionTargetOut(
        id=row.id,
        name=row.name,
        kind=row.kind,
        config=redact(raw_cfg),
        mode=row.mode,
        enabled=bool(row.enabled),
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


@router.get("", response_model=CursorPage[ActionTargetOut])
async def list_targets(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    include_deleted: bool = False,
) -> CursorPage[ActionTargetOut]:
    stmt = select(ActionTarget)
    if not include_deleted:
        stmt = stmt.where(ActionTarget.deleted_at.is_(None))
    if cursor:
        stmt = stmt.where(ActionTarget.id > cursor)
    stmt = stmt.order_by(ActionTarget.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    next_cursor = rows[limit].id if len(rows) > limit else None
    rows = rows[:limit]
    return CursorPage[ActionTargetOut](items=[_to_out(r) for r in rows], next_cursor=next_cursor)


@router.get("/{target_id}", response_model=ActionTargetOut)
async def get_target(
    target_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> ActionTargetOut:
    row = await session.get(ActionTarget, target_id)
    if row is None or row.deleted_at is not None:
        raise not_found("action_target.not_found", target_id)
    return _to_out(row)


@router.post("", status_code=201, response_model=ActionTargetOut)
async def create_target(
    body: ActionTargetCreate,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ActionTargetOut:
    if body.kind not in ALLOWED_KINDS:
        raise bad_request("action_target.invalid_kind", f"kind must be one of {sorted(ALLOWED_KINDS)}")
    if body.mode not in ALLOWED_MODES:
        raise bad_request("action_target.invalid_mode", f"mode must be one of {sorted(ALLOWED_MODES)}")
    clash = await session.scalar(select(ActionTarget).where(ActionTarget.name == body.name))
    if clash is not None:
        raise conflict("action_target.name_taken", f"Action target {body.name!r} already exists")
    tid = new_id("act")
    row = ActionTarget(
        id=tid,
        name=body.name,
        kind=body.kind,
        config=json.dumps(body.config),
        mode=body.mode,
        enabled=1 if body.enabled else 0,
        created_at=utcnow_iso(),
    )
    session.add(row)
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="create_action_target",
        target_kind="action_target",
        target_id=tid,
        outcome="applied",
        payload_summary={"name": body.name, "kind": body.kind, "mode": body.mode},
    )
    return _to_out(row)


@router.patch("/{target_id}", response_model=ActionTargetOut)
async def patch_target(
    target_id: str,
    body: ActionTargetUpdate,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ActionTargetOut:
    row = await session.get(ActionTarget, target_id)
    if row is None or row.deleted_at is not None:
        raise not_found("action_target.not_found", target_id)
    if body.name is not None and body.name != row.name:
        clash = await session.scalar(
            select(ActionTarget).where(ActionTarget.name == body.name, ActionTarget.id != target_id)
        )
        if clash is not None:
            raise conflict("action_target.name_taken", "name collision")
        row.name = body.name
    if body.config is not None:
        row.config = json.dumps(body.config)
    if body.mode is not None:
        if body.mode not in ALLOWED_MODES:
            raise bad_request("action_target.invalid_mode", "Invalid mode")
        row.mode = body.mode
    if body.enabled is not None:
        row.enabled = 1 if body.enabled else 0
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="update_action_target",
        target_kind="action_target",
        target_id=target_id,
        outcome="applied",
    )
    return _to_out(row)


@router.delete("/{target_id}", status_code=204)
async def delete_target(
    target_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    row = await session.get(ActionTarget, target_id)
    if row is None or row.deleted_at is not None:
        raise not_found("action_target.not_found", target_id)
    row.deleted_at = utcnow_iso()
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="delete_action_target",
        target_kind="action_target",
        target_id=target_id,
        outcome="applied",
    )
    return Response(status_code=204)


@router.post("/{target_id}/test", response_model=ActionTargetTestResult)
async def test_target(
    target_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> ActionTargetTestResult:
    """Dry-run a target's configuration. Phase 1: just validates that the target
    exists and its config is parseable. Real dispatch lands in Phase 4."""
    row = await session.get(ActionTarget, target_id)
    if row is None or row.deleted_at is not None:
        raise not_found("action_target.not_found", target_id)
    # TODO Phase 4: actually dispatch by kind (webhook/local_script/etc.).
    try:
        cfg = json.loads(row.config or "{}")
    except json.JSONDecodeError as exc:
        return ActionTargetTestResult(
            ok=False, message="config is not valid JSON", details={"error": str(exc)}
        )
    return ActionTargetTestResult(
        ok=True,
        message="Target appears well-formed (Phase 1: no live dispatch).",
        details={"kind": row.kind, "mode": row.mode, "config_keys": sorted(cfg.keys())},
    )
