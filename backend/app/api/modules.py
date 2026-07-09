"""Admin module endpoints."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import modules as module_registry
from ..approval.apply import dispatch_target
from ..auth.deps import CurrentUser, require_csrf, require_session
from ..db import get_session, read_session
from ..errors import bad_request, not_found, precondition_failed
from ..events.publish import publish_after_commit
from ..ids import new_id
from ..models import ActionTarget, Module, Page, utcnow_iso
from ..schemas import CursorPage, ModuleCreate, ModuleOut, ModulePatch, ReorderIn
from ..services.audit import write_event
from ..services.etag import parse_if_match, weak_etag
from . import _idem


def _module_event_summary(row: Module) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "page_id": row.page_id,
        "position": row.position,
        "version": row.version,
        "updated_at": row.updated_at,
        "owner_kind": row.owner_kind,
        "owner_id": row.owner_id,
    }

router = APIRouter(prefix="/api/v1/modules", tags=["modules"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _to_out(row: Module) -> ModuleOut:
    return ModuleOut(
        id=row.id,
        type=row.type,
        title=row.title,
        owner_kind=row.owner_kind,
        owner_id=row.owner_id,
        page_id=row.page_id,
        position=row.position,
        grid=json.loads(row.grid) if row.grid else None,
        permissions=json.loads(row.permissions or "{}"),
        data=json.loads(row.data or "{}"),
        config=json.loads(row.config or "{}"),
        schema_version=row.schema_version,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_updated_by=row.last_updated_by,
        deleted_at=row.deleted_at,
    )


def _validate_payload(module_type: str, data: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        clean_data = module_registry.validate_data(module_type, data)
        clean_config = module_registry.validate_config(module_type, config)
    except KeyError:
        raise bad_request("module.unknown_type", f"Unknown module type: {module_type}") from None
    except Exception as exc:  # ValidationError
        raise bad_request("module.invalid_payload", str(exc)) from exc
    return clean_data, clean_config


# ---------------------------------------------------------------------------
# list / get
# ---------------------------------------------------------------------------


@router.get("", response_model=CursorPage[ModuleOut])
async def list_modules(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
    page_id: str | None = None,
    type: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    include_deleted: bool = False,
) -> CursorPage[ModuleOut]:
    stmt = select(Module)
    if not include_deleted:
        stmt = stmt.where(Module.deleted_at.is_(None))
    if page_id is not None:
        stmt = stmt.where(Module.page_id == page_id)
    if type is not None:
        stmt = stmt.where(Module.type == type)
    if cursor:
        stmt = stmt.where(Module.id > cursor)
    stmt = stmt.order_by(Module.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    next_cursor = rows[limit].id if len(rows) > limit else None
    rows = rows[:limit]
    return CursorPage[ModuleOut](items=[_to_out(r) for r in rows], next_cursor=next_cursor)


@router.get("/{module_id}", response_model=ModuleOut)
async def get_module(
    module_id: str,
    response: Response,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> ModuleOut:
    row = await session.get(Module, module_id)
    if row is None or row.deleted_at is not None:
        raise not_found("module.not_found", module_id)
    response.headers["ETag"] = weak_etag(row.version)
    return _to_out(row)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_module(
    body: ModuleCreate,
    request: Request,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    idem_key = _idem.header(request)
    cached = await _idem.lookup(session, tool="POST /modules", key=idem_key)
    if cached is not None:
        return JSONResponse(content=cached, status_code=201, headers={"X-Idempotency-Replay": "true"})

    # Page must exist
    page = await session.get(Page, body.page_id)
    if page is None or page.deleted_at is not None:
        raise not_found("page.not_found", body.page_id)

    # _validate_payload raises module.unknown_type for an unknown type, so no
    # separate pre-check is needed here.
    clean_data, clean_config = _validate_payload(body.type, body.data, body.config)

    now = utcnow_iso()
    mod_id = new_id("mod")
    row = Module(
        id=mod_id,
        type=body.type,
        title=body.title,
        owner_kind=body.owner_kind,
        owner_id=body.owner_id,
        page_id=body.page_id,
        position=body.position,
        grid=json.dumps(body.grid) if body.grid is not None else None,
        permissions=json.dumps(body.permissions),
        data=json.dumps(clean_data),
        config=json.dumps(clean_config),
        schema_version=1,
        version=1,
        created_at=now,
        updated_at=now,
        last_updated_by="user:admin",
    )
    session.add(row)
    await session.flush()

    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="create_module",
        target_kind="module",
        target_id=mod_id,
        outcome="applied",
        payload_summary={"type": body.type, "page_id": body.page_id},
    )

    summary = _module_event_summary(row)
    publish_after_commit(session, f"page:{body.page_id}", "module_added", {"module": summary})
    publish_after_commit(session, f"module:{mod_id}", "module_added", {"module": summary})

    out = _to_out(row).model_dump()
    await _idem.save(session, tool="POST /modules", key=idem_key, response=out)
    return JSONResponse(content=out, status_code=201, headers={"ETag": weak_etag(row.version)})


# ---------------------------------------------------------------------------
# patch
# ---------------------------------------------------------------------------


@router.patch("/{module_id}", response_model=ModuleOut)
async def patch_module(
    module_id: str,
    body: ModulePatch,
    response: Response,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ModuleOut:
    row = await session.get(Module, module_id)
    if row is None or row.deleted_at is not None:
        raise not_found("module.not_found", module_id)

    expected_version = parse_if_match(if_match)
    if expected_version is not None and expected_version != row.version:
        raise precondition_failed("module.etag_mismatch", "Module version mismatch")

    # Re-validate data/config if either is being changed.
    new_data = json.loads(row.data) if body.data is None else body.data
    new_config = json.loads(row.config) if body.config is None else body.config
    if body.data is not None or body.config is not None:
        clean_data, clean_config = _validate_payload(row.type, new_data, new_config)
        new_data, new_config = clean_data, clean_config

    if body.title is not None:
        row.title = body.title
    if body.position is not None:
        row.position = body.position
    if body.grid is not None:
        row.grid = json.dumps(body.grid)
    if body.permissions is not None:
        row.permissions = json.dumps(body.permissions)
    if body.data is not None:
        row.data = json.dumps(new_data)
    if body.config is not None:
        row.config = json.dumps(new_config)
    if body.page_id is not None:
        page = await session.get(Page, body.page_id)
        if page is None or page.deleted_at is not None:
            raise not_found("page.not_found", body.page_id)
        row.page_id = body.page_id

    row.version += 1
    row.updated_at = utcnow_iso()
    row.last_updated_by = "user:admin"
    await session.flush()

    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="update_module_data" if body.data is not None else "update_module_meta",
        target_kind="module",
        target_id=module_id,
        outcome="applied",
        payload_summary={"version": row.version},
    )

    summary = _module_event_summary(row)
    publish_after_commit(session, f"page:{row.page_id}", "module_updated", {"module": summary})
    publish_after_commit(session, f"module:{module_id}", "module_updated", {"module": summary})

    response.headers["ETag"] = weak_etag(row.version)
    return _to_out(row)


# ---------------------------------------------------------------------------
# delete (soft)
# ---------------------------------------------------------------------------


@router.delete("/{module_id}", status_code=204)
async def delete_module(
    module_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    row = await session.get(Module, module_id)
    if row is None or row.deleted_at is not None:
        raise not_found("module.not_found", module_id)
    row.deleted_at = utcnow_iso()
    row.version += 1
    row.updated_at = row.deleted_at
    row.last_updated_by = "user:admin"
    page_id_at_delete = row.page_id
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="delete_module",
        target_kind="module",
        target_id=module_id,
        outcome="applied",
    )
    publish_after_commit(
        session, f"page:{page_id_at_delete}", "module_removed", {"module_id": module_id}
    )
    publish_after_commit(
        session, f"module:{module_id}", "module_removed", {"module_id": module_id}
    )
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# reorder
# ---------------------------------------------------------------------------


@router.post("/{module_id}/fire")
async def fire_action_button(
    module_id: str,
    body: dict[str, Any] | None = None,
    _: Annotated[CurrentUser, Depends(require_csrf)] = None,  # type: ignore[assignment]
    session: Annotated[AsyncSession, Depends(get_session)] = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Admin-side firing of an action_button module.

    Bypasses the approval engine (admin mutations always do) and
    dispatches the resolved action target inline. Writes ``data.last_result``
    back onto the module and audit-logs the firing.
    """
    row = await session.get(Module, module_id)
    if row is None or row.deleted_at is not None:
        raise not_found("module.not_found", module_id)
    if row.type != "action_button":
        raise bad_request(
            "module.wrong_type",
            f"module {module_id} is not an action_button (got {row.type})",
        )
    data = json.loads(row.data or "{}")
    target_id = data.get("action_target_id")
    if not target_id:
        raise bad_request("module.no_target", "action_button has no action_target_id")
    target = await session.get(ActionTarget, target_id)
    if target is None or target.deleted_at is not None:
        raise not_found("action_target.not_found", target_id)
    if not target.enabled:
        raise bad_request("action_target.disabled", f"target {target_id} disabled")
    payload = (body or {}).get("payload") or {}
    result = await dispatch_target(
        session, target, payload, from_actor="user:admin"
    )
    # Update last_result on the module.
    data["last_result"] = {
        "fired_at": utcnow_iso(),
        "ok": bool(result.get("ok")),
        "message": result.get("error") or result.get("body_preview") or None,
        "details": result,
    }
    try:
        clean_data = module_registry.validate_data(row.type, data)
    except Exception as exc:
        # If the resulting last_result fails validation (overly long message,
        # etc.), drop the details and retry with a minimal shape.
        data["last_result"] = {
            "fired_at": data["last_result"]["fired_at"],
            "ok": data["last_result"]["ok"],
        }
        try:
            clean_data = module_registry.validate_data(row.type, data)
        except Exception as exc2:  # noqa: BLE001
            raise bad_request("module.invalid_payload", str(exc2)) from exc
    row.data = json.dumps(clean_data)
    row.version += 1
    row.updated_at = utcnow_iso()
    row.last_updated_by = "user:admin"
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="fire_action_button",
        target_kind="action_target",
        target_id=target_id,
        outcome="applied" if result.get("ok") else "error",
        payload_summary={"module_id": module_id, "target_id": target_id},
        error_detail=(result.get("error") if not result.get("ok") else None),
    )
    summary = _module_event_summary(row)
    publish_after_commit(session, f"page:{row.page_id}", "module_updated", {"module": summary})
    publish_after_commit(session, f"module:{module_id}", "module_updated", {"module": summary})
    return {
        "ok": bool(result.get("ok")),
        "result": result,
        "module_version": row.version,
    }


@router.post("/reorder")
async def reorder_modules(
    body: ReorderIn,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    if not body.page_id:
        raise bad_request("module.reorder_page_id_required", "page_id required for module reorder")
    page = await session.get(Page, body.page_id)
    if page is None or page.deleted_at is not None:
        raise not_found("page.not_found", body.page_id)

    rows = (
        await session.execute(
            select(Module).where(
                Module.page_id == body.page_id, Module.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    by_id = {r.id: r for r in rows}
    missing = [mid for mid in body.ids if mid not in by_id]
    if missing:
        raise bad_request(
            "module.reorder_unknown_id",
            f"Module IDs not on page {body.page_id}: {missing}",
        )
    if len(set(body.ids)) != len(body.ids):
        raise bad_request("module.reorder_duplicates", "duplicate IDs in reorder list")

    now = utcnow_iso()
    for position, module_id in enumerate(body.ids):
        row = by_id[module_id]
        if row.position != position:
            row.position = position
            row.version += 1
            row.updated_at = now
            row.last_updated_by = "user:admin"
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="update_module_meta",
        target_kind="page",
        target_id=body.page_id,
        outcome="applied",
        payload_summary={"reorder_count": len(body.ids)},
    )
    publish_after_commit(
        session,
        f"page:{body.page_id}",
        "modules_reordered",
        {"page_id": body.page_id, "order": list(body.ids)},
    )
    return {"reordered": len(body.ids)}
