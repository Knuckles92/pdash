"""Admin page endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import CurrentUser, require_csrf, require_session
from ..db import get_session, read_session
from ..errors import bad_request, conflict, not_found
from ..events.publish import publish_after_commit
from ..ids import new_id
from ..models import Page, utcnow_iso
from ..schemas import (
    CursorPage,
    DefaultExamplesMutationOut,
    PageCreate,
    PageOut,
    PagePatch,
    ReorderIn,
)
from ..services.audit import write_event
from ..services.home_examples import clear_default_examples, deploy_default_examples
from . import _idem


def _page_event_summary(row: Page) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "kind": row.kind,
        "owner_kind": row.owner_kind,
        "owner_id": row.owner_id,
        "deleted_at": row.deleted_at,
    }

router = APIRouter(prefix="/api/v1/pages", tags=["pages"])

ALLOWED_KINDS = {"home", "agent", "custom", "system", "corkboard", "canvas"}


def _to_out(row: Page) -> PageOut:
    return PageOut(
        id=row.id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        kind=row.kind,
        owner_kind=row.owner_kind,
        owner_id=row.owner_id,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )


@router.get("", response_model=CursorPage[PageOut])
async def list_pages(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    include_deleted: bool = False,
) -> CursorPage[PageOut]:
    stmt = select(Page)
    if not include_deleted:
        stmt = stmt.where(Page.deleted_at.is_(None))
    if cursor:
        stmt = stmt.where(Page.id > cursor)
    stmt = stmt.order_by(Page.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    next_cursor = rows[limit].id if len(rows) > limit else None
    rows = rows[:limit]
    return CursorPage[PageOut](items=[_to_out(r) for r in rows], next_cursor=next_cursor)


@router.get("/by-slug/{slug}", response_model=PageOut)
async def get_page_by_slug(
    slug: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> PageOut:
    row = await session.scalar(
        select(Page).where(Page.slug == slug, Page.deleted_at.is_(None))
    )
    if row is None:
        raise not_found("page.not_found", slug)
    return _to_out(row)


@router.get("/{page_id}", response_model=PageOut)
async def get_page(
    page_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> PageOut:
    row = await session.get(Page, page_id)
    if row is None or row.deleted_at is not None:
        raise not_found("page.not_found", page_id)
    return _to_out(row)


@router.post("", status_code=201)
async def create_page(
    body: PageCreate,
    request: Request,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    if body.kind not in ALLOWED_KINDS:
        raise bad_request("page.invalid_kind", f"kind must be one of {sorted(ALLOWED_KINDS)}")
    idem_key = _idem.header(request)
    cached = await _idem.lookup(session, tool="POST /pages", key=idem_key)
    if cached is not None:
        return JSONResponse(content=cached, status_code=201, headers={"X-Idempotency-Replay": "true"})

    # slug must be unique
    existing = await session.scalar(select(Page).where(Page.slug == body.slug))
    if existing is not None:
        raise conflict("page.slug_taken", f"Page with slug {body.slug!r} already exists")

    pid = new_id("pg")
    row = Page(
        id=pid,
        slug=body.slug,
        name=body.name,
        description=body.description,
        kind=body.kind,
        owner_kind=body.owner_kind,
        owner_id=body.owner_id,
        created_at=utcnow_iso(),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise conflict("page.slug_taken", "Page slug collision") from exc

    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="create_page",
        target_kind="page",
        target_id=pid,
        outcome="applied",
        payload_summary={"slug": body.slug, "kind": body.kind},
    )
    publish_after_commit(session, "pages", "page_added", {"page": _page_event_summary(row)})
    out = _to_out(row).model_dump()
    await _idem.save(session, tool="POST /pages", key=idem_key, response=out)
    return JSONResponse(content=out, status_code=201)


async def _require_home_page(session: AsyncSession, page_id: str) -> Page:
    row = await session.get(Page, page_id)
    if row is None or row.deleted_at is not None:
        raise not_found("page.not_found", page_id)
    if row.kind != "home":
        raise bad_request("page.not_home", "Default examples are only available on the home page")
    return row


@router.delete("/{page_id}/default-examples", response_model=DefaultExamplesMutationOut)
async def clear_page_default_examples(
    page_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DefaultExamplesMutationOut:
    await _require_home_page(session, page_id)
    cleared = await clear_default_examples(session, page_id)
    return DefaultExamplesMutationOut(cleared=cleared)


@router.post("/{page_id}/default-examples", response_model=DefaultExamplesMutationOut)
async def deploy_page_default_examples(
    page_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DefaultExamplesMutationOut:
    await _require_home_page(session, page_id)
    deployed = await deploy_default_examples(session, page_id)
    return DefaultExamplesMutationOut(deployed=deployed)


@router.patch("/{page_id}", response_model=PageOut)
async def patch_page(
    page_id: str,
    body: PagePatch,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PageOut:
    row = await session.get(Page, page_id)
    if row is None or row.deleted_at is not None:
        raise not_found("page.not_found", page_id)

    if body.slug is not None and body.slug != row.slug:
        clash = await session.scalar(select(Page).where(Page.slug == body.slug, Page.id != page_id))
        if clash is not None:
            raise conflict("page.slug_taken", f"Page with slug {body.slug!r} already exists")
        row.slug = body.slug
    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        # Page meta updates intentionally reuse the module-meta action_type so
        # they surface in the activity feed; there is no dedicated page-meta type.
        action_type="update_module_meta",
        target_kind="page",
        target_id=page_id,
        outcome="applied",
    )
    publish_after_commit(session, "pages", "page_updated", {"page": _page_event_summary(row)})
    return _to_out(row)


@router.delete("/{page_id}", status_code=204)
async def delete_page(
    page_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    row = await session.get(Page, page_id)
    if row is None or row.deleted_at is not None:
        raise not_found("page.not_found", page_id)
    if row.kind == "home":
        raise bad_request("page.cannot_delete_home", "The home page cannot be deleted")
    row.deleted_at = utcnow_iso()
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="delete_page",
        target_kind="page",
        target_id=page_id,
        outcome="applied",
    )
    publish_after_commit(session, "pages", "page_removed", {"page_id": page_id})
    return Response(status_code=204)


@router.post("/reorder")
async def reorder_pages(
    body: ReorderIn,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    # Pages don't have a position column in v1; ordering is by id (ULID time-order)
    # at the data layer. For now we accept the reorder call and just verify the IDs
    # exist — clients can use this to validate before any UX flow ships.
    rows = (await session.execute(select(Page).where(Page.deleted_at.is_(None)))).scalars().all()
    by_id = {r.id: r for r in rows}
    missing = [pid for pid in body.ids if pid not in by_id]
    if missing:
        raise bad_request("page.reorder_unknown_id", f"Unknown page IDs: {missing}")
    return {"reordered": len(body.ids), "note": "Page order is currently ID-based; persistent order column is deferred."}
