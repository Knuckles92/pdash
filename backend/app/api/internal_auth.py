"""Auth dependencies for the ``/api/v1/internal/*`` surface.

Two checks per request:

1. ``Authorization: Bearer <service_secret>`` — matches the secret stored in
   ``kv_settings`` under :data:`KEY_SERVICE_SECRET`.
2. ``X-Agent-Id: <agent_id>`` — must correspond to an existing agent row
   whose ``status == 'active'``. Disabled/revoked → ``403 agent.disabled``.

CSRF is bypassed (no browser cookies are involved on this surface).

Rate limiting is *not* enforced in this dependency — it is applied at the
route level so we can distinguish read/write buckets.

This module also exposes ``POST /api/v1/internal/auth/resolve-key``: the MCP
server holds raw agent API keys (presented by the AI client) and needs to
resolve them to an ``agent_id`` so subsequent ``/internal/*`` calls can send
the standard ``X-Agent-Id`` header. Authenticated by service secret only (no
``X-Agent-Id`` is sent — this *is* the lookup). Argon2 hashes embed a random
salt, so the verification is a scan over active agents: O(N_agents) per call.
The MCP server caches successful resolutions for 30s so steady-state cost is
roughly one verify per agent per cache window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.passwords import verify_password
from ..auth.secrets import KEY_SERVICE_SECRET, get_kv
from ..db import get_session, read_session
from ..errors import ProblemDetail, forbidden, unauthorized
from ..models import Agent, utcnow_iso


@dataclass
class CallingAgent:
    """The agent making the call, resolved from ``X-Agent-Id``."""

    id: str
    display_name: str
    permissions: str  # JSON string (raw)


async def _require_service_secret(
    request: Request,
    session: AsyncSession,
) -> None:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise unauthorized("auth.service_secret_missing", "Bearer token required")
    presented = auth.split(" ", 1)[1].strip()
    expected = await get_kv(session, KEY_SERVICE_SECRET)
    if not expected or presented != expected:
        raise unauthorized("auth.service_secret_invalid", "service secret mismatch")


async def calling_agent(
    request: Request,
    session: Annotated[AsyncSession, Depends(read_session)],
    x_agent_id: Annotated[str | None, Header(alias="X-Agent-Id")] = None,
) -> CallingAgent:
    """Resolve the calling agent for internal endpoints.

    Raises:
        401 ``auth.service_secret_missing|invalid`` — bad Bearer.
        400 ``agent.id_required`` — missing X-Agent-Id.
        403 ``agent.unknown`` — X-Agent-Id has no matching row.
        403 ``agent.disabled`` — status is not 'active'.
    """
    await _require_service_secret(request, session)
    if not x_agent_id:
        raise ProblemDetail(
            status=400,
            code="agent.id_required",
            title="Bad Request",
            detail="X-Agent-Id header required on internal endpoints",
        )
    row = await session.get(Agent, x_agent_id)
    if row is None:
        raise forbidden("agent.unknown", f"agent {x_agent_id} not found")
    if row.status != "active":
        raise forbidden("agent.disabled", f"agent status is {row.status!r}")
    return CallingAgent(
        id=row.id,
        display_name=row.display_name,
        permissions=row.permissions or "{}",
    )


# ---------------------------------------------------------------------------
# resolve-key endpoint (MCP server lookup path)
# ---------------------------------------------------------------------------


router = APIRouter(prefix="/api/v1/internal/auth", tags=["internal"])


class ResolveKeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(..., min_length=8, max_length=200)


class ResolveKeyOut(BaseModel):
    agent_id: str
    display_name: str
    status: str
    permissions: dict


@router.post("/resolve-key", response_model=ResolveKeyOut)
async def resolve_key(
    body: ResolveKeyIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResolveKeyOut:
    """Resolve an agent API key (``hb_agt_...``) to an ``agent_id``.

    Auth: service secret only. The MCP server calls this after extracting the
    ``Authorization: Bearer hb_agt_...`` header from the calling AI client.

    Returns 401 ``auth.api_key_invalid`` for unknown keys *or* keys whose
    agent has a non-active status (so a revoked key is indistinguishable
    from a never-existed one from the caller's perspective).

    Successful lookups bump the agent's ``last_active_at``.
    """
    await _require_service_secret(request, session)
    # Cheap prefix gate: every agent API key must start with hb_agt_
    if not body.api_key.startswith("hb_agt_"):
        raise unauthorized("auth.api_key_invalid", "unknown API key")

    # Argon2 hashes embed a salt — scan active agents and verify each.
    # Practical cost: dozens of agents at most for this single-admin product.
    rows = (
        await session.execute(
            select(Agent).where(Agent.status == "active")
        )
    ).scalars().all()
    for row in rows:
        if verify_password(row.api_key_hash, body.api_key):
            row.last_active_at = utcnow_iso()
            await session.flush()
            return ResolveKeyOut(
                agent_id=row.id,
                display_name=row.display_name,
                status=row.status,
                permissions=json.loads(row.permissions or "{}"),
            )
    raise unauthorized("auth.api_key_invalid", "unknown API key")


__all__ = ["CallingAgent", "calling_agent", "router"]
