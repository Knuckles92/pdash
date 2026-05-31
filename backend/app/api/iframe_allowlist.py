"""Iframe allowlist endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import CurrentUser, require_csrf, require_session
from ..db import get_session, read_session
from ..errors import conflict, not_found
from ..models import IframeAllowlist, utcnow_iso
from ..schemas import IframeAllowlistCreate, IframeAllowlistOut
from ..services.audit import write_event

router = APIRouter(prefix="/api/v1/iframe-allowlist", tags=["iframe-allowlist"])


def _to_out(row: IframeAllowlist) -> IframeAllowlistOut:
    return IframeAllowlistOut(
        id=row.id,
        host_pattern=row.host_pattern,
        path_prefix=row.path_prefix,
        description=row.description,
        added_at=row.added_at,
    )


@router.get("", response_model=list[IframeAllowlistOut])
async def list_entries(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> list[IframeAllowlistOut]:
    rows = (await session.execute(select(IframeAllowlist).order_by(IframeAllowlist.id))).scalars().all()
    return [_to_out(r) for r in rows]


@router.get("/{entry_id}", response_model=IframeAllowlistOut)
async def get_entry(
    entry_id: int,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> IframeAllowlistOut:
    row = await session.get(IframeAllowlist, entry_id)
    if row is None:
        raise not_found("iframe_allowlist.not_found", str(entry_id))
    return _to_out(row)


@router.post("", status_code=201, response_model=IframeAllowlistOut)
async def add_entry(
    body: IframeAllowlistCreate,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IframeAllowlistOut:
    row = IframeAllowlist(
        host_pattern=body.host_pattern,
        path_prefix=body.path_prefix,
        description=body.description,
        added_at=utcnow_iso(),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise conflict("iframe_allowlist.duplicate", "host_pattern already allowlisted") from exc
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="add_iframe_allowlist",
        target_kind="iframe_allowlist",
        target_id=str(row.id),
        outcome="applied",
        payload_summary={"host_pattern": body.host_pattern},
    )
    return _to_out(row)


@router.delete("/{entry_id}", status_code=204)
async def remove_entry(
    entry_id: int,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    row = await session.get(IframeAllowlist, entry_id)
    if row is None:
        raise not_found("iframe_allowlist.not_found", str(entry_id))
    await session.delete(row)
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="remove_iframe_allowlist",
        target_kind="iframe_allowlist",
        target_id=str(entry_id),
        outcome="applied",
    )
    return Response(status_code=204)
