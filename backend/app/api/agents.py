"""Admin agent endpoints."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import CurrentUser, require_csrf, require_session
from ..db import get_session, read_session
from ..errors import bad_request, conflict, not_found
from ..ids import new_id
from ..models import Agent, utcnow_iso
from ..schemas import AgentCreate, AgentKeyOut, AgentOut, AgentUpdate, CursorPage
from ..services.agent_keys import generate_agent_api_key
from ..services.audit import write_event
from . import _idem

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _to_out(row: Agent) -> AgentOut:
    return AgentOut(
        id=row.id,
        display_name=row.display_name,
        description=row.description,
        permissions=json.loads(row.permissions or "{}"),
        status=row.status,
        created_at=row.created_at,
        last_active_at=row.last_active_at,
        last_key_rotated_at=row.last_key_rotated_at,
    )


@router.get("", response_model=CursorPage[AgentOut])
async def list_agents(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[AgentOut]:
    stmt = select(Agent)
    if cursor:
        stmt = stmt.where(Agent.id > cursor)
    stmt = stmt.order_by(Agent.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    next_cursor = rows[limit].id if len(rows) > limit else None
    rows = rows[:limit]
    return CursorPage[AgentOut](items=[_to_out(r) for r in rows], next_cursor=next_cursor)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> AgentOut:
    row = await session.get(Agent, agent_id)
    if row is None:
        raise not_found("agent.not_found", agent_id)
    return _to_out(row)


@router.post("", status_code=201)
async def create_agent(
    body: AgentCreate,
    request: Request,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    idem_key = _idem.header(request)
    cached = await _idem.lookup(session, tool="POST /agents", key=idem_key)
    if cached is not None:
        return JSONResponse(content=cached, status_code=201, headers={"X-Idempotency-Replay": "true"})

    clash = await session.scalar(select(Agent).where(Agent.display_name == body.display_name))
    if clash is not None:
        raise conflict("agent.name_taken", f"Agent {body.display_name!r} already exists")

    plaintext, hashed = generate_agent_api_key()
    aid = new_id("agt")
    row = Agent(
        id=aid,
        display_name=body.display_name,
        description=body.description,
        api_key_hash=hashed,
        permissions=json.dumps(body.permissions),
        status="active",
        created_at=utcnow_iso(),
        last_key_rotated_at=utcnow_iso(),
    )
    session.add(row)
    await session.flush()

    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="create_agent",
        target_kind="agent",
        target_id=aid,
        outcome="applied",
        payload_summary={"display_name": body.display_name},
    )

    out = AgentKeyOut(agent=_to_out(row), api_key=plaintext).model_dump()
    await _idem.save(session, tool="POST /agents", key=idem_key, response=out)
    return JSONResponse(content=out, status_code=201)


@router.patch("/{agent_id}", response_model=AgentOut)
async def patch_agent(
    agent_id: str,
    body: AgentUpdate,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentOut:
    row = await session.get(Agent, agent_id)
    if row is None:
        raise not_found("agent.not_found", agent_id)
    if body.display_name is not None and body.display_name != row.display_name:
        clash = await session.scalar(
            select(Agent).where(Agent.display_name == body.display_name, Agent.id != agent_id)
        )
        if clash is not None:
            raise conflict("agent.name_taken", "Agent display_name collision")
        row.display_name = body.display_name
    if body.description is not None:
        row.description = body.description
    if body.permissions is not None:
        row.permissions = json.dumps(body.permissions)
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="update_agent",
        target_kind="agent",
        target_id=agent_id,
        outcome="applied",
    )
    return _to_out(row)


@router.delete("/{agent_id}", status_code=204)
async def revoke_agent(
    agent_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Agents are never hard-deleted; DELETE flips status to revoked."""
    row = await session.get(Agent, agent_id)
    if row is None:
        raise not_found("agent.not_found", agent_id)
    row.status = "revoked"
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="revoke_agent",
        target_kind="agent",
        target_id=agent_id,
        outcome="applied",
    )
    return JSONResponse(status_code=204, content=None)


@router.post("/{agent_id}/rotate-key", status_code=200)
async def rotate_key(
    agent_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentKeyOut:
    row = await session.get(Agent, agent_id)
    if row is None:
        raise not_found("agent.not_found", agent_id)
    if row.status == "revoked":
        raise bad_request("agent.revoked", "Cannot rotate a revoked agent's key")
    plaintext, hashed = generate_agent_api_key()
    row.api_key_hash = hashed
    row.last_key_rotated_at = utcnow_iso()
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="rotate_agent_key",
        target_kind="agent",
        target_id=agent_id,
        outcome="applied",
    )
    return AgentKeyOut(agent=_to_out(row), api_key=plaintext)


@router.post("/{agent_id}/enable", response_model=AgentOut)
async def enable_agent(
    agent_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentOut:
    row = await session.get(Agent, agent_id)
    if row is None:
        raise not_found("agent.not_found", agent_id)
    if row.status == "revoked":
        raise bad_request("agent.revoked", "Revoked agents cannot be enabled; create a new agent")
    row.status = "active"
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="enable_agent",
        target_kind="agent",
        target_id=agent_id,
        outcome="applied",
    )
    return _to_out(row)


@router.post("/{agent_id}/disable", response_model=AgentOut)
async def disable_agent(
    agent_id: str,
    _: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentOut:
    row = await session.get(Agent, agent_id)
    if row is None:
        raise not_found("agent.not_found", agent_id)
    if row.status == "revoked":
        raise bad_request("agent.revoked", "Revoked agents cannot be disabled")
    row.status = "disabled"
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="disable_agent",
        target_kind="agent",
        target_id=agent_id,
        outcome="applied",
    )
    return _to_out(row)
