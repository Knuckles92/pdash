"""Internal endpoints (``/api/v1/internal/*``) — MCP-facing.

Auth: ``Authorization: Bearer <service_secret>`` + ``X-Agent-Id: <agent_id>``.
Required ``Idempotency-Key`` header on POSTs. CSRF is bypassed.

Every POST routes through the approval engine (orchestrator.submit_request)
and returns one of:

- ``200 {status:"applied", ...}``  — engine auto-approved + apply succeeded.
- ``202 {status:"pending", request_id, expires_at}``  — queued for admin.
- ``403 {status:"denied_by_rule", rule_id, request_id}`` — denied by rule.

Errors use RFC 7807 with ``request_id`` cross-referencing activity_log when
relevant. An ``X-Audit-Id`` header is set on every response that wrote an
activity_log row.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Sequence
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import modules as module_registry
from ..approval import lifecycle
from ..approval.apply import ApplyError, apply_append_log
from ..approval.engine import DecisionRequest, decide
from ..approval.expiry import compute_expires_at
from ..approval.orchestrator import submit_request
from ..auth.cookies import SessionPayload, sign_session
from ..auth.secrets import KEY_SERVICE_SECRET, get_kv, get_signing_secret
from ..config import get_settings
from ..db import get_session, read_session
from ..errors import ProblemDetail, bad_request, not_found, precondition_failed
from ..events.publish import publish_after_commit
from ..ids import new_id
from ..models import (
    ActionTarget,
    ApprovalRequest,
    FileRecord,
    Module,
    Page,
    utcnow_iso,
)
from ..modules import MODULE_TYPES, health
from ..schemas import (
    AppendLogIn,
    DeleteModuleIn,
    FileDropboxOut,
    FileDropboxPage,
    FireActionIn,
    ProposeModuleIn,
    ProposePageIn,
    RegisterFileIn,
    UpdateModuleIn,
    ValidateModuleIn,
    WhoAmIOut,
)
from ..services.audit import write_event
from ..services.etag import parse_if_match
from ..services.files import (
    FilePathError,
    classify_kind,
    file_to_dict,
    guess_mime,
    page_inbox_dir,
    resolve_inbox_file,
    stat_and_sha256,
)
from ..services.rate_limit import consume as rl_consume
from . import _agent_idem
from .internal_auth import CallingAgent, calling_agent

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


# ---------------------------------------------------------------------------
# Rate limit helpers
# ---------------------------------------------------------------------------


async def _rate_limit(
    agent_id: str,
    *,
    kind: str,
    session: AsyncSession | None = None,
) -> None:
    """Persistent token-bucket rate limit (Phase 6).

    On write endpoints the caller passes the active session so the bucket
    update rides in the same transaction; on read endpoints (which don't
    open a writer) the rate-limit consume opens its own short-lived
    session.
    """
    allowed, retry_after = await rl_consume(agent_id, kind=kind, session=session)
    if not allowed:
        raise ProblemDetail(
            status=429,
            code="rate_limit.exceeded",
            title="Too Many Requests",
            detail=f"Rate limit exceeded; retry in {math.ceil(retry_after)}s",
            headers={"Retry-After": str(math.ceil(retry_after))},
            extra={"retry_after_ms": int(retry_after * 1000)},
        )


# ---------------------------------------------------------------------------
# Response shaping helpers
# ---------------------------------------------------------------------------


def _module_to_dict(row: Module) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "owner_kind": row.owner_kind,
        "owner_id": row.owner_id,
        "page_id": row.page_id,
        "position": row.position,
        "grid": json.loads(row.grid) if row.grid else None,
        "permissions": json.loads(row.permissions or "{}"),
        "data": json.loads(row.data or "{}"),
        "config": json.loads(row.config or "{}"),
        "schema_version": row.schema_version,
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_updated_by": row.last_updated_by,
        "deleted_at": row.deleted_at,
    }


def _module_with_health(row: Module) -> dict[str, Any]:
    """Serialize a module and annotate whether its stored payload still renders.

    ``health`` is ``{render_ok, type_known, errors}`` — an agent can scan a list
    of these to find broken widgets without re-deriving validity itself.
    """
    out = _module_to_dict(row)
    out["health"] = health.render_status(out)
    return out


def _invalid_payload_problem(errors: list[dict[str, Any]]) -> ProblemDetail:
    detail = "; ".join(f"{e['section']}.{e['loc']}: {e['msg']}" for e in errors)
    return ProblemDetail(
        status=400,
        code="module.invalid_payload",
        title="Bad Request",
        detail=detail or "invalid module payload",
        # Structured per-field errors so an agent can fix the exact field rather
        # than parse a flattened string.
        extra={"errors": errors},
    )


def _clean_or_raise(section: str, module_type: str, payload: Any) -> dict[str, Any]:
    """Validate + normalize a ``data``/``config`` payload for storage.

    Raises a structured ``module.invalid_payload`` (with per-field ``errors``) on
    a schema violation, mirroring what :func:`validate_module` reports for a
    dry run.
    """
    validator = (
        module_registry.validate_data
        if section == "data"
        else module_registry.validate_config
    )
    try:
        return validator(module_type, payload)
    except ValidationError as exc:
        raise _invalid_payload_problem(
            health.format_validation_error(section, exc)
        ) from exc
    except KeyError as exc:
        raise bad_request(
            "module.unknown_type", f"Unknown module type: {module_type}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 — non-pydantic failure, keep the string
        raise bad_request("module.invalid_payload", str(exc)) from exc


def _page_slice(rows: Sequence[Any], limit: int) -> tuple[list[Any], str | None]:
    """Split a fetch-(limit+1) result into ``(page_rows, next_cursor)``.

    The cursor is the LAST RETURNED row's id — not the look-ahead row — so the
    next page's ``id > cursor`` filter resumes immediately after it. (Setting it
    to the look-ahead row's id would skip exactly one row per page boundary.)
    """
    has_more = len(rows) > limit
    page_rows = list(rows[:limit])
    next_cursor = page_rows[-1].id if (has_more and page_rows) else None
    return page_rows, next_cursor


def _attach_audit_header(response: Response | JSONResponse, audit_id: int | None) -> None:
    if audit_id is not None:
        response.headers["X-Audit-Id"] = str(audit_id)


async def _orchestrate_response(
    *,
    result,
    session: AsyncSession,
    tool: str,
    agent_id: str,
    idem_key: str,
    extra_applied: dict[str, Any] | None = None,
) -> JSONResponse:
    """Translate an orchestrator result into the standard internal triad response."""
    audit_id = result.audit_id
    body: dict[str, Any]
    if result.status == "applied":
        status_code = 200
        body = {
            "status": "applied",
            "request_id": result.request.id,
            "applied_at": result.request.applied_at,
        }
        if result.apply_result is not None:
            body.update(result.apply_result.extra)
            if extra_applied is not None:
                body.update(extra_applied)
    elif result.status == "pending":
        status_code = 202
        body = {
            "status": "pending",
            "request_id": result.request.id,
            "expires_at": result.request.expires_at,
        }
    elif result.status == "denied":
        status_code = 403
        body = {
            "status": "denied_by_rule",
            "rule_id": result.decision.rule_id,
            "request_id": result.request.id,
        }
    else:  # application_failed
        status_code = 500
        body = {
            "status": "application_failed",
            "request_id": result.request.id,
            "error": str(result.apply_error) if result.apply_error else "unknown",
        }

    # Shared tail: cache idempotent response + build the JSON response once.
    await _agent_idem.save(
        session, agent_id=agent_id, tool=tool, key=idem_key,
        response={"_status_code": status_code, "body": body, "audit_id": audit_id},
        request_id=result.request.id,
    )
    resp = JSONResponse(content=body, status_code=status_code)
    _attach_audit_header(resp, audit_id)
    return resp


async def _cached_or_none(
    session: AsyncSession, *, agent_id: str, tool: str, idem_key: str
) -> JSONResponse | None:
    cached = await _agent_idem.lookup(
        session, agent_id=agent_id, tool=tool, key=idem_key
    )
    if cached is None:
        return None
    status_code = cached.get("_status_code", 200)
    body = cached.get("body", {})
    headers = {"X-Idempotency-Replay": "true"}
    if cached.get("audit_id") is not None:
        headers["X-Audit-Id"] = str(cached["audit_id"])
    return JSONResponse(content=body, status_code=status_code, headers=headers)


async def _begin_write(
    request: Request,
    agent: CallingAgent,
    session: AsyncSession,
    *,
    tool: str,
) -> tuple[str, JSONResponse | None]:
    """Common opening steps for every internal POST handler.

    Charges the write rate limit, reads the required ``Idempotency-Key``, and
    looks up a cached response. Returns ``(idem_key, cached_response_or_None)``;
    a non-None response means the handler should return it immediately (replay).
    """
    await _rate_limit(agent.id, kind="write", session=session)
    idem_key = _agent_idem.require_header(request)
    cached = await _cached_or_none(session, agent_id=agent.id, tool=tool, idem_key=idem_key)
    return idem_key, cached


def _slugify(name: str) -> str:
    """Derive a URL slug from a page name; falls back to ``"page"`` when empty."""
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40]
    return slug or "page"


# ---------------------------------------------------------------------------
# whoami
# ---------------------------------------------------------------------------


@router.get("/whoami", response_model=WhoAmIOut)
async def whoami(
    agent: Annotated[CallingAgent, Depends(calling_agent)],
) -> WhoAmIOut:
    await _rate_limit(agent.id, kind="read")
    return WhoAmIOut(
        agent={
            "id": agent.id,
            "display_name": agent.display_name,
            "permissions": json.loads(agent.permissions or "{}"),
        }
    )


# ---------------------------------------------------------------------------
# module-schema/{type}
# ---------------------------------------------------------------------------


@router.get("/module-schema/{module_type}")
async def get_module_schema(
    module_type: str,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
) -> dict:
    await _rate_limit(agent.id, kind="read")
    try:
        return module_registry.schema_for(module_type)
    except KeyError as exc:
        raise not_found("module_schema.not_found", module_type) from exc


# ---------------------------------------------------------------------------
# my-modules
# ---------------------------------------------------------------------------


@router.get("/my-modules")
async def my_modules(
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
    page_id: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict:
    await _rate_limit(agent.id, kind="read")
    limit = max(1, min(limit, 200))
    stmt = select(Module).where(
        Module.deleted_at.is_(None),
        Module.owner_kind == "agent",
        Module.owner_id == agent.id,
    )
    if page_id:
        stmt = stmt.where(Module.page_id == page_id)
    if cursor:
        stmt = stmt.where(Module.id > cursor)
    stmt = stmt.order_by(Module.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    page_rows, next_cursor = _page_slice(rows, limit)
    items = [_module_to_dict(row) for row in page_rows]
    return {"items": items, "next_cursor": next_cursor}


# ---------------------------------------------------------------------------
# my-pending-requests
# ---------------------------------------------------------------------------


@router.get("/my-pending-requests")
async def my_pending_requests(
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
    cursor: str | None = None,
    limit: int = 50,
    status_filter: str | None = None,
) -> dict:
    await _rate_limit(agent.id, kind="read")
    limit = max(1, min(limit, 200))
    statuses = (
        [s.strip() for s in status_filter.split(",") if s.strip()]
        if status_filter
        else ["pending"]
    )
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.agent_id == agent.id,
        ApprovalRequest.status.in_(statuses),
    )
    if cursor:
        stmt = stmt.where(ApprovalRequest.id > cursor)
    stmt = stmt.order_by(ApprovalRequest.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    page_rows, next_cursor = _page_slice(rows, limit)
    items = [
        {
            "id": row.id,
            "action_type": row.action_type,
            "target_kind": row.target_kind,
            "target_id": row.target_id,
            "status": row.status,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "decided_at": row.decided_at,
            "decided_by": row.decided_by,
            # Surface the admin's (or rule's) note so the agent can act on the
            # guidance instead of blindly re-proposing a denied write.
            "decision_reason": row.decision_reason,
        }
        for row in page_rows
    ]
    return {"items": items, "next_cursor": next_cursor}


# ---------------------------------------------------------------------------
# module-schemas — discover every available widget type at once
# ---------------------------------------------------------------------------


@router.get("/module-schemas")
async def list_module_schemas(
    agent: Annotated[CallingAgent, Depends(calling_agent)],
) -> dict:
    """Return the JSON Schema for every module type, for widget discovery.

    Saves an agent from having to know type names up front (the single-type
    ``/module-schema/{type}`` still works for fetching just one).
    """
    await _rate_limit(agent.id, kind="read")
    return {
        "types": list(MODULE_TYPES),
        "items": [module_registry.schema_for(t) for t in MODULE_TYPES],
    }


# ---------------------------------------------------------------------------
# modules/{id} — fetch one module by id (any owner, single-tenant)
# ---------------------------------------------------------------------------


@router.get("/modules/{module_id}")
async def get_module(
    module_id: str,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> dict:
    """Fetch a single module by id, with an ``owned`` flag + render ``health``.

    Single-tenant: an agent may read any live module (so it can see admin-owned
    widgets on a shared page it contributes to), but ``owned`` tells it whether
    it can edit without admin approval.
    """
    await _rate_limit(agent.id, kind="read")
    mod = await session.get(Module, module_id)
    if mod is None or mod.deleted_at is not None:
        raise not_found("module.not_found", module_id)
    out = _module_with_health(mod)
    out["owned"] = mod.owner_kind == "agent" and mod.owner_id == agent.id
    return out


# ---------------------------------------------------------------------------
# pages — list every page (so agents can find where to place widgets)
# ---------------------------------------------------------------------------


@router.get("/pages")
async def list_pages(
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
    cursor: str | None = None,
    limit: int = 50,
) -> dict:
    """List all live pages with module counts and an ``owned`` flag.

    Replaces the old MCP-side scan that could only see pages the agent already
    had modules on — agents can now discover any page to propose widgets onto.
    """
    await _rate_limit(agent.id, kind="read")
    limit = max(1, min(limit, 200))
    stmt = select(Page).where(Page.deleted_at.is_(None))
    if cursor:
        stmt = stmt.where(Page.id > cursor)
    stmt = stmt.order_by(Page.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    page_rows, next_cursor = _page_slice(rows, limit)

    page_ids = [p.id for p in page_rows]
    total_counts: dict[str, int] = {}
    my_counts: dict[str, int] = {}
    if page_ids:
        base = (
            select(Module.page_id, func.count())
            .where(Module.page_id.in_(page_ids), Module.deleted_at.is_(None))
            .group_by(Module.page_id)
        )
        for pid, count in (await session.execute(base)).all():
            total_counts[pid] = count
        mine = base.where(Module.owner_kind == "agent", Module.owner_id == agent.id)
        for pid, count in (await session.execute(mine)).all():
            my_counts[pid] = count

    items = [
        {
            "id": p.id,
            "slug": p.slug,
            "name": p.name,
            "kind": p.kind,
            "owner_kind": p.owner_kind,
            "owner_id": p.owner_id,
            "owned": p.owner_kind == "agent" and p.owner_id == agent.id,
            "module_count": total_counts.get(p.id, 0),
            "my_module_count": my_counts.get(p.id, 0),
        }
        for p in page_rows
    ]
    return {"items": items, "next_cursor": next_cursor}


# ---------------------------------------------------------------------------
# pages/{id}/render — structured "what does this dashboard look like" view
# ---------------------------------------------------------------------------


@router.get("/pages/{page_id}/render")
async def render_page(
    page_id: str,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> dict:
    """Return a structured render of a page: ordered modules + layout + health.

    This is the headless equivalent of looking at the dashboard — every module
    (regardless of owner) in display order, an ASCII grid sketch, and which
    modules would fail to render. Pair with ``screenshot_page`` for real pixels.
    """
    await _rate_limit(agent.id, kind="read")
    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is not None:
        raise not_found("page.not_found", page_id)
    rows = (
        await session.execute(
            select(Module)
            .where(Module.page_id == page_id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.created_at)
        )
    ).scalars().all()
    modules = health.order_modules([_module_with_health(r) for r in rows])
    broken = [m["id"] for m in modules if not m["health"]["render_ok"]]
    return {
        "page": {"id": page.id, "name": page.name, "slug": page.slug, "kind": page.kind},
        "modules": modules,
        "layout": health.layout_summary(modules),
        "broken_module_ids": broken,
        "summary": {"total": len(modules), "broken": len(broken)},
    }


# ---------------------------------------------------------------------------
# module-health — which of my modules are broken (and why)?
# ---------------------------------------------------------------------------


@router.get("/module-health")
async def module_health(
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
    page_id: str | None = None,
    only_broken: bool = False,
    cursor: str | None = None,
    limit: int = 50,
) -> dict:
    """Report render health for the agent's owned modules (paginated).

    Each item carries ``render_ok`` + structured ``errors`` so the agent can
    feed the exact problem into ``update_module``. ``only_broken=true`` filters
    the current page to just the broken ones. ``checked`` counts how many were
    evaluated this page (a no-results page with a ``next_cursor`` means keep
    paging).
    """
    await _rate_limit(agent.id, kind="read")
    limit = max(1, min(limit, 200))
    stmt = select(Module).where(
        Module.deleted_at.is_(None),
        Module.owner_kind == "agent",
        Module.owner_id == agent.id,
    )
    if page_id:
        stmt = stmt.where(Module.page_id == page_id)
    if cursor:
        stmt = stmt.where(Module.id > cursor)
    stmt = stmt.order_by(Module.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    page_rows, next_cursor = _page_slice(rows, limit)

    items = []
    for row in page_rows:
        status = health.render_status(_module_to_dict(row))
        if only_broken and status["render_ok"]:
            continue
        items.append(
            {
                "id": row.id,
                "type": row.type,
                "title": row.title,
                "page_id": row.page_id,
                "schema_version": row.schema_version,
                "version": row.version,
                "updated_at": row.updated_at,
                **status,
            }
        )
    return {"items": items, "next_cursor": next_cursor, "checked": len(page_rows)}


# ---------------------------------------------------------------------------
# validate-module — dry-run a payload against a type schema (no write)
# ---------------------------------------------------------------------------


@router.post("/validate-module")
async def validate_module(
    body: ValidateModuleIn,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
) -> dict:
    """Validate a proposed ``data``/``config`` against a type schema, no side effects.

    Lets an agent confirm a widget payload is well-formed BEFORE proposing it,
    instead of discovering an invalid field via a rejected write. Returns
    ``{ok, type_known, errors:[{section, loc, msg, type}]}``.
    """
    await _rate_limit(agent.id, kind="read")
    return health.validate_payload(body.type, body.data, body.config)


# ---------------------------------------------------------------------------
# pages/{id}/screenshot — real PNG of the live dashboard (via sidecar)
# ---------------------------------------------------------------------------


def _frontend_page_url(base: str, page: Page) -> str:
    base = base.rstrip("/")
    # The home page renders at "/"; everything else at "/pages/<slug>".
    if page.kind == "home" or page.slug == "home":
        return f"{base}/"
    return f"{base}/pages/{page.slug}"


@router.get("/pages/{page_id}/screenshot")
async def screenshot_page(
    page_id: str,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
    viewport_width: int | None = None,
    full_page: bool = True,
) -> Response:
    """Render the live frontend page in headless Chromium and return a PNG.

    The backend mints a short-lived admin session cookie and hands it to the
    screenshot sidecar (single admin → the agent sees what the admin sees).
    Returns 501 ``screenshot.unavailable`` when no sidecar is configured.
    """
    await _rate_limit(agent.id, kind="read")
    settings = get_settings()
    service_url = settings.screenshot_service_url
    if not service_url:
        raise ProblemDetail(
            status=501,
            code="screenshot.unavailable",
            title="Not Implemented",
            detail=(
                "Screenshot service is not configured. Set "
                "PDASH_SCREENSHOT_SERVICE_URL to enable dashboard screenshots."
            ),
        )

    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is not None:
        raise not_found("page.not_found", page_id)

    signing_secret = await get_signing_secret(session)
    now = int(time.time())
    token = sign_session(
        SessionPayload(
            user_id="admin",
            issued_at=now,
            expires_at=now + settings.screenshot_session_ttl_seconds,
            # Read-only scope: even if this short-lived cookie leaks, it can only
            # render pages, never write through the admin API (see auth/deps.py).
            audience="screenshot",
        ),
        signing_secret,
    )
    target_url = _frontend_page_url(settings.frontend_url, page)
    width = viewport_width or settings.screenshot_default_viewport_width
    width = max(360, min(width, 3840))

    capture_body = {
        "url": target_url,
        # Inject the session cookie for the frontend origin; secure=false so it
        # rides the internal HTTP hop the sidecar uses to reach the frontend.
        "cookies": [
            {
                "name": settings.session_cookie_name,
                "value": token,
                "url": settings.frontend_url,
            }
        ],
        "viewport_width": width,
        "full_page": full_page,
    }
    service_secret = await get_kv(session, KEY_SERVICE_SECRET)
    headers = {"Authorization": f"Bearer {service_secret}"} if service_secret else {}

    try:
        async with httpx.AsyncClient(
            timeout=settings.screenshot_timeout_seconds
        ) as client:
            resp = await client.post(
                service_url.rstrip("/") + "/capture",
                json=capture_body,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise ProblemDetail(
            status=502,
            code="screenshot.failed",
            title="Bad Gateway",
            detail=f"screenshot service unreachable: {exc}",
        ) from exc
    if resp.status_code != 200:
        raise ProblemDetail(
            status=502,
            code="screenshot.failed",
            title="Bad Gateway",
            detail=f"screenshot service returned {resp.status_code}: {resp.text[:300]}",
        )
    return Response(
        content=resp.content,
        media_type="image/png",
        headers={"X-Screenshot-Url": target_url},
    )


# ---------------------------------------------------------------------------
# propose-module
# ---------------------------------------------------------------------------


@router.post("/propose-module")
async def propose_module(
    body: ProposeModuleIn,
    request: Request,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    TOOL = "POST /internal/propose-module"
    idem_key, cached = await _begin_write(request, agent, session, tool=TOOL)
    if cached is not None:
        return cached

    # Validate the page and module type up front (cheap fail).
    page = await session.get(Page, body.page_id)
    if page is None or page.deleted_at is not None:
        raise not_found("page.not_found", body.page_id)
    if body.type not in MODULE_TYPES:
        raise bad_request("module.unknown_type", f"Unknown module type: {body.type}")
    clean_data = _clean_or_raise("data", body.type, body.data)
    clean_config = _clean_or_raise("config", body.type, body.config)

    # Mint a provisional module_id so the agent can echo it back later.
    provisional_id = new_id("mod")
    proposed_payload = {
        "type": body.type,
        "page_id": body.page_id,
        "title": body.title,
        "position": body.position,
        "grid": body.grid,
        "permissions": body.permissions,
        "data": clean_data,
        "config": clean_config,
        "provisional_id": provisional_id,
    }
    result = await submit_request(
        session,
        agent_id=agent.id,
        action_type="create_module",
        target_kind="module",
        target_id=provisional_id,
        proposed_payload=proposed_payload,
        module_type=body.type,
        page_id=body.page_id,
        agent_owns_target=True,  # creator owns their own creation
        idempotency_key=idem_key,
        rationale=body.rationale,
    )

    extra_applied: dict[str, Any] | None = None
    if result.status == "applied" and result.apply_result is not None:
        mod = await session.get(Module, result.apply_result.target_id)
        if mod is not None:
            extra_applied = {"module": _module_to_dict(mod)}
    return await _orchestrate_response(
        result=result,
        session=session,
        tool=TOOL,
        agent_id=agent.id,
        idem_key=idem_key,
        extra_applied=extra_applied,
    )


# ---------------------------------------------------------------------------
# update-module
# ---------------------------------------------------------------------------


def _action_type_for_patch(patch_dict: dict[str, Any]) -> str:
    if "data" in patch_dict:
        return "update_module_data"
    if "config" in patch_dict:
        return "update_module_config"
    # title / position / page_id all count as "meta"
    return "update_module_meta"


@router.post("/update-module")
async def update_module(
    body: UpdateModuleIn,
    request: Request,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    TOOL = "POST /internal/update-module"
    idem_key, cached = await _begin_write(request, agent, session, tool=TOOL)
    if cached is not None:
        return cached

    mod = await session.get(Module, body.id)
    if mod is None or mod.deleted_at is not None:
        raise not_found("module.not_found", body.id)

    # ETag check happens BEFORE enqueueing (per spec).
    if body.expected_etag is not None:
        expected = parse_if_match(body.expected_etag)
        if expected is not None and expected != mod.version:
            raise precondition_failed(
                "concurrency.stale",
                f"Module {body.id} version {mod.version}, client expected {expected}",
            )

    patch_dict = body.patch.model_dump(exclude_none=True)
    if not patch_dict:
        raise bad_request("module.empty_patch", "patch must have at least one field")
    # If `data`/`config` are being changed, re-validate now (against the merged
    # view, but only the changed key gets sent in proposed_payload).
    if "data" in patch_dict:
        patch_dict["data"] = _clean_or_raise("data", mod.type, patch_dict["data"])
    if "config" in patch_dict:
        patch_dict["config"] = _clean_or_raise("config", mod.type, patch_dict["config"])

    action_type = _action_type_for_patch(patch_dict)
    proposed_payload = {"id": body.id, "patch": patch_dict}
    agent_owns_target = mod.owner_kind == "agent" and mod.owner_id == agent.id

    result = await submit_request(
        session,
        agent_id=agent.id,
        action_type=action_type,
        target_kind="module",
        target_id=body.id,
        proposed_payload=proposed_payload,
        module_type=mod.type,
        page_id=mod.page_id,
        agent_owns_target=agent_owns_target,
        idempotency_key=idem_key,
        rationale=body.rationale,
    )

    extra_applied: dict[str, Any] | None = None
    if result.status == "applied":
        refreshed = await session.get(Module, body.id)
        if refreshed is not None:
            extra_applied = {"module": _module_to_dict(refreshed)}
    return await _orchestrate_response(
        result=result,
        session=session,
        tool=TOOL,
        agent_id=agent.id,
        idem_key=idem_key,
        extra_applied=extra_applied,
    )


# ---------------------------------------------------------------------------
# delete-module
# ---------------------------------------------------------------------------


@router.post("/delete-module")
async def delete_module(
    body: DeleteModuleIn,
    request: Request,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    TOOL = "POST /internal/delete-module"
    idem_key, cached = await _begin_write(request, agent, session, tool=TOOL)
    if cached is not None:
        return cached

    mod = await session.get(Module, body.id)
    if mod is None or mod.deleted_at is not None:
        raise not_found("module.not_found", body.id)
    if body.expected_etag is not None:
        expected = parse_if_match(body.expected_etag)
        if expected is not None and expected != mod.version:
            raise precondition_failed(
                "concurrency.stale",
                f"Module {body.id} version {mod.version}, client expected {expected}",
            )

    agent_owns_target = mod.owner_kind == "agent" and mod.owner_id == agent.id
    proposed_payload = {"id": body.id}
    result = await submit_request(
        session,
        agent_id=agent.id,
        action_type="delete_module",
        target_kind="module",
        target_id=body.id,
        proposed_payload=proposed_payload,
        module_type=mod.type,
        page_id=mod.page_id,
        agent_owns_target=agent_owns_target,
        idempotency_key=idem_key,
        rationale=body.rationale,
    )
    return await _orchestrate_response(
        result=result,
        session=session,
        tool=TOOL,
        agent_id=agent.id,
        idem_key=idem_key,
    )


# ---------------------------------------------------------------------------
# append-log — special path (built-in rule auto-applies for owners)
# ---------------------------------------------------------------------------


@router.post("/append-log")
async def append_log(
    body: AppendLogIn,
    request: Request,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    """Append log lines to a ``log_stream`` module.

    The built-in ``update_module_data on owner_scope=self`` rule auto-approves
    this when the agent owns the module; otherwise the engine routes it to
    ``prompt`` like any other update. On auto-approval we apply directly via
    :func:`apply_append_log`, bypassing the heavier ``apply_update_module``
    path because log appends carry their own merge/trim semantics.
    """
    TOOL = "POST /internal/append-log"
    idem_key, cached = await _begin_write(request, agent, session, tool=TOOL)
    if cached is not None:
        return cached

    mod = await session.get(Module, body.module_id)
    if mod is None or mod.deleted_at is not None:
        raise not_found("module.not_found", body.module_id)
    if mod.type != "log_stream":
        raise bad_request(
            "module.wrong_type",
            f"module {body.module_id} is not a log_stream (got {mod.type})",
        )
    agent_owns_target = mod.owner_kind == "agent" and mod.owner_id == agent.id

    # Quick engine decision; on auto_approve we apply via apply_append_log.
    decision = await decide(
        session,
        DecisionRequest(
            action_type="update_module_data",
            agent_id=agent.id,
            module_type="log_stream",
            module_id=body.module_id,
            page_id=mod.page_id,
            agent_owns_target=agent_owns_target,
        ),
    )

    # Build a request row even on auto_approve so audit + idempotency
    # references hang together.
    request_id = new_id("apr")
    lines = [ln.model_dump(exclude_none=True) for ln in body.lines]
    payload = {"module_id": body.module_id, "lines": lines}
    now = utcnow_iso()
    apr = ApprovalRequest(
        id=request_id,
        agent_id=agent.id,
        action_type="update_module_data",
        target_kind="module",
        target_id=body.module_id,
        proposed_payload=json.dumps(payload, separators=(",", ":"), default=str),
        idempotency_key=idem_key,
        status="pending",
        created_at=now,
        decision_reason=body.rationale,
    )
    session.add(apr)
    await session.flush()

    if decision.status == "auto_approve":
        lifecycle.mark_approved(
            apr,
            decided_by=f"rule:{decision.rule_id}" if decision.rule_id else "system:auto",
            decision_reason=body.rationale,
        )
        try:
            res = await apply_append_log(
                session,
                module_id=body.module_id,
                lines=lines,
                actor=f"agent:{agent.id}",
            )
            lifecycle.mark_applied(apr)
        except ApplyError as exc:
            lifecycle.mark_application_failed(apr, reason=str(exc))
            log = await write_event(
                session,
                actor_kind="rule" if decision.rule_id else "system",
                actor_id=decision.rule_id or "auto",
                action_type="update_module_data",
                target_kind="module",
                target_id=body.module_id,
                outcome="error",
                payload_summary={
                    "apply_error": str(exc),
                    "lines": len(lines),
                    "rule_id": decision.rule_id,
                },
                request_id=request_id,
                rule_id=decision.rule_id,
                error_detail=str(exc),
            )
            err_body = {"status": "application_failed", "request_id": request_id, "error": str(exc)}
            await _agent_idem.save(
                session, agent_id=agent.id, tool=TOOL,
                key=idem_key,
                response={"_status_code": 500, "body": err_body, "audit_id": log.id},
                request_id=request_id,
            )
            resp = JSONResponse(content=err_body, status_code=500)
            _attach_audit_header(resp, log.id)
            return resp
        log = await write_event(
            session,
            actor_kind="rule" if decision.rule_id else "system",
            actor_id=decision.rule_id or "auto",
            action_type="update_module_data",
            target_kind="module",
            target_id=body.module_id,
            outcome="auto_approved",
            payload_summary={
                "lines": len(lines),
                "appended": res["appended"],
                "truncated_count": res["truncated_count"],
                "rule_id": decision.rule_id,
            },
            request_id=request_id,
            rule_id=decision.rule_id,
        )
        publish_after_commit(
            session,
            "approvals",
            "approval_decided",
            {
                "request_id": request_id,
                "agent_id": agent.id,
                "action_type": "update_module_data",
                "target_kind": "module",
                "target_id": body.module_id,
                "outcome": "applied",
                "rule_id": decision.rule_id,
                "decided_at": apr.decided_at,
                "applied_at": apr.applied_at,
            },
        )
        body_out = {
            "status": "applied",
            "request_id": request_id,
            "appended": res["appended"],
            "buffer_size": res["buffer_size"],
        }
        if res["truncated_count"]:
            body_out["truncated_count"] = res["truncated_count"]
        await _agent_idem.save(
            session, agent_id=agent.id, tool=TOOL,
            key=idem_key,
            response={"_status_code": 200, "body": body_out, "audit_id": log.id},
            request_id=request_id,
        )
        resp = JSONResponse(content=body_out, status_code=200)
        _attach_audit_header(resp, log.id)
        return resp

    if decision.status == "deny":
        lifecycle.mark_denied(
            apr,
            decided_by=f"rule:{decision.rule_id}" if decision.rule_id else "system:deny",
            decision_reason=body.rationale or "denied by rule",
        )
        log = await write_event(
            session,
            actor_kind="rule" if decision.rule_id else "system",
            actor_id=decision.rule_id or "deny",
            action_type="update_module_data",
            target_kind="module",
            target_id=body.module_id,
            outcome="denied",
            payload_summary={"lines": len(lines), "rule_id": decision.rule_id},
            request_id=request_id,
            rule_id=decision.rule_id,
        )
        publish_after_commit(
            session,
            "approvals",
            "approval_decided",
            {
                "request_id": request_id,
                "agent_id": agent.id,
                "action_type": "update_module_data",
                "target_kind": "module",
                "target_id": body.module_id,
                "outcome": "denied",
                "rule_id": decision.rule_id,
                "decided_at": apr.decided_at,
            },
        )
        body_out = {
            "status": "denied_by_rule",
            "rule_id": decision.rule_id,
            "request_id": request_id,
        }
        await _agent_idem.save(
            session, agent_id=agent.id, tool=TOOL,
            key=idem_key,
            response={"_status_code": 403, "body": body_out, "audit_id": log.id},
            request_id=request_id,
        )
        resp = JSONResponse(content=body_out, status_code=403)
        _attach_audit_header(resp, log.id)
        return resp

    apr.expires_at = compute_expires_at()
    log = await write_event(
        session,
        actor_kind="agent",
        actor_id=agent.id,
        action_type="update_module_data",
        target_kind="module",
        target_id=body.module_id,
        outcome="queued",
        payload_summary={"lines": len(lines)},
        request_id=request_id,
    )
    publish_after_commit(
        session,
        "approvals",
        "approval_pending",
        {
            "request_id": request_id,
            "agent_id": agent.id,
            "action_type": "update_module_data",
            "target_kind": "module",
            "target_id": body.module_id,
            "module_type": "log_stream",
            "page_id": mod.page_id,
            "created_at": apr.created_at,
            "expires_at": apr.expires_at,
        },
    )
    body_out = {
        "status": "pending",
        "request_id": request_id,
        "expires_at": apr.expires_at,
    }
    await _agent_idem.save(
        session, agent_id=agent.id, tool=TOOL,
        key=idem_key,
        response={"_status_code": 202, "body": body_out, "audit_id": log.id},
        request_id=request_id,
    )
    resp = JSONResponse(content=body_out, status_code=202)
    _attach_audit_header(resp, log.id)
    return resp


# ---------------------------------------------------------------------------
# fire-action
# ---------------------------------------------------------------------------


@router.post("/fire-action")
async def fire_action(
    body: FireActionIn,
    request: Request,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    TOOL = "POST /internal/fire-action"
    idem_key, cached = await _begin_write(request, agent, session, tool=TOOL)
    if cached is not None:
        return cached

    target = await session.get(ActionTarget, body.target_id)
    if target is None or target.deleted_at is not None:
        raise not_found("action_target.not_found", body.target_id)

    payload = {"target_id": body.target_id, "payload": body.payload or {}}
    result = await submit_request(
        session,
        agent_id=agent.id,
        action_type="fire_action_button",
        target_kind="action_target",
        target_id=body.target_id,
        proposed_payload=payload,
        agent_owns_target=False,  # action targets aren't owned by agents
        idempotency_key=idem_key,
        rationale=body.rationale,
    )

    extra_applied: dict[str, Any] | None = None
    if result.status == "applied" and result.apply_result is not None:
        extra_applied = {"result": result.apply_result.extra.get("execution_result")}
    return await _orchestrate_response(
        result=result,
        session=session,
        tool=TOOL,
        agent_id=agent.id,
        idem_key=idem_key,
        extra_applied=extra_applied,
    )


# ---------------------------------------------------------------------------
# propose-page
# ---------------------------------------------------------------------------


@router.post("/propose-page")
async def propose_page(
    body: ProposePageIn,
    request: Request,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    TOOL = "POST /internal/propose-page"
    idem_key, cached = await _begin_write(request, agent, session, tool=TOOL)
    if cached is not None:
        return cached

    # Derive a slug if missing.
    slug = body.slug or _slugify(body.name)

    # Validate uniqueness up front (cheap fail).
    existing = await session.scalar(select(Page).where(Page.slug == slug))
    if existing is not None:
        raise ProblemDetail(
            status=409, code="page.slug_taken",
            title="Conflict", detail=f"slug {slug!r} taken",
        )

    provisional_id = new_id("pg")
    proposed_payload = {
        "name": body.name,
        "slug": slug,
        "description": body.description,
        "kind": body.kind,
        "provisional_id": provisional_id,
    }
    result = await submit_request(
        session,
        agent_id=agent.id,
        action_type="create_page",
        target_kind="page",
        target_id=provisional_id,
        proposed_payload=proposed_payload,
        agent_owns_target=True,
        idempotency_key=idem_key,
        rationale=body.rationale,
    )
    extra_applied: dict[str, Any] | None = None
    if result.status == "applied" and result.apply_result is not None:
        page = await session.get(Page, result.apply_result.target_id)
        if page is not None:
            extra_applied = {
                "page": {
                    "id": page.id,
                    "slug": page.slug,
                    "name": page.name,
                    "kind": page.kind,
                    "created_at": page.created_at,
                }
            }
    return await _orchestrate_response(
        result=result,
        session=session,
        tool=TOOL,
        agent_id=agent.id,
        idem_key=idem_key,
        extra_applied=extra_applied,
    )


# ---------------------------------------------------------------------------
# file-dropbox — discover where to drop files
# ---------------------------------------------------------------------------


@router.get("/file-dropbox", response_model=FileDropboxOut)
async def file_dropbox(
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
    page_id: str | None = None,
) -> FileDropboxOut:
    """Return the inbox path(s) the agent should drop files into.

    ``pages`` lists the dashboards the agent already works on (owns a module on),
    each with its absolute ``drop_path``. Passing ``page_id`` creates+returns that
    page's drop dir as ``target``. After writing the file, call ``register_file``
    with the bare filename and the same ``page_id``.
    """
    await _rate_limit(agent.id, kind="read")
    settings = get_settings()
    inbox_root = settings.resolved_files_inbox_path()

    owned_page_ids = (
        await session.execute(
            select(Module.page_id)
            .where(
                Module.deleted_at.is_(None),
                Module.owner_kind == "agent",
                Module.owner_id == agent.id,
            )
            .distinct()
        )
    ).scalars().all()

    pages_out: list[FileDropboxPage] = []
    if owned_page_ids:
        prows = (
            await session.execute(
                select(Page)
                .where(Page.id.in_(owned_page_ids), Page.deleted_at.is_(None))
                .order_by(Page.name)
            )
        ).scalars().all()
        pages_out = [
            FileDropboxPage(
                page_id=p.id,
                slug=p.slug,
                name=p.name,
                drop_path=str(page_inbox_dir(inbox_root, p.id)),
            )
            for p in prows
        ]

    target: str | None = None
    if page_id is not None:
        page = await session.get(Page, page_id)
        if page is None or page.deleted_at is not None:
            raise not_found("page.not_found", page_id)
        drop_dir = page_inbox_dir(inbox_root, page_id)
        drop_dir.mkdir(parents=True, exist_ok=True)
        target = str(drop_dir)

    return FileDropboxOut(
        inbox_root=str(inbox_root),
        target=target,
        pages=pages_out,
        max_bytes=settings.file_max_bytes,
        mime_allowlist=settings.file_mime_allowlist,
        guidance=(
            "Write your file into 'target' (pass page_id to get one) or a page's "
            "drop_path, then call register_file with the bare filename and the same "
            "page_id. Files for no particular page can be dropped in inbox_root and "
            "registered without page_id."
        ),
    )


# ---------------------------------------------------------------------------
# my-files — list files this agent has registered
# ---------------------------------------------------------------------------


@router.get("/my-files")
async def my_files(
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(read_session)],
    cursor: str | None = None,
    limit: int = 50,
) -> dict:
    await _rate_limit(agent.id, kind="read")
    limit = max(1, min(limit, 200))
    stmt = select(FileRecord).where(
        FileRecord.agent_id == agent.id,
        FileRecord.status == "registered",
    )
    if cursor:
        stmt = stmt.where(FileRecord.id > cursor)
    stmt = stmt.order_by(FileRecord.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    page_rows, next_cursor = _page_slice(rows, limit)
    items = [file_to_dict(row) for row in page_rows]
    return {"items": items, "next_cursor": next_cursor}


# ---------------------------------------------------------------------------
# register-file — claim a dropped file (through the approval engine)
# ---------------------------------------------------------------------------


@router.post("/register-file")
async def register_file(
    body: RegisterFileIn,
    request: Request,
    agent: Annotated[CallingAgent, Depends(calling_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    TOOL = "POST /internal/register-file"
    idem_key, cached = await _begin_write(request, agent, session, tool=TOOL)
    if cached is not None:
        return cached

    settings = get_settings()

    # Optional page hint must exist if provided.
    if body.page_id is not None:
        page = await session.get(Page, body.page_id)
        if page is None or page.deleted_at is not None:
            raise not_found("page.not_found", body.page_id)

    # Resolve + validate the dropped file (reject path traversal).
    inbox_root = settings.resolved_files_inbox_path()
    try:
        src = resolve_inbox_file(inbox_root, body.page_id, body.inbox_name)
    except FilePathError as exc:
        raise bad_request("file.invalid_name", str(exc)) from exc
    if not src.is_file():
        raise not_found("file.not_in_inbox", body.inbox_name)

    # Capture size/sha/mime AT SUBMIT TIME; apply re-checks they're unchanged.
    size, sha = stat_and_sha256(src)
    if size > settings.file_max_bytes:
        raise bad_request(
            "file.too_large",
            f"{size} bytes exceeds the {settings.file_max_bytes}-byte limit",
        )
    mime = guess_mime(body.inbox_name)
    if settings.file_mime_allowlist and mime not in settings.file_mime_allowlist:
        raise bad_request("file.mime_not_allowed", f"MIME type {mime!r} is not allowed")
    kind = classify_kind(mime)

    provisional_id = new_id("fil")
    proposed_payload = {
        "inbox_name": body.inbox_name,
        "display_name": body.display_name,
        "kind": kind,
        "mime": mime,
        "sha256": sha,
        "size_bytes": size,
        "page_id": body.page_id,
        "purpose": body.purpose,
        "provisional_id": provisional_id,
    }
    result = await submit_request(
        session,
        agent_id=agent.id,
        action_type="register_file",
        target_kind=None,
        target_id=provisional_id,
        proposed_payload=proposed_payload,
        page_id=body.page_id,
        agent_owns_target=True,  # the agent registering owns the file
        idempotency_key=idem_key,
        rationale=body.rationale,
    )

    extra_applied: dict[str, Any] | None = None
    if result.status == "applied" and result.apply_result is not None:
        frow = await session.get(FileRecord, result.apply_result.target_id)
        if frow is not None:
            extra_applied = {"file": file_to_dict(frow)}
    return await _orchestrate_response(
        result=result,
        session=session,
        tool=TOOL,
        agent_id=agent.id,
        idem_key=idem_key,
        extra_applied=extra_applied,
    )
