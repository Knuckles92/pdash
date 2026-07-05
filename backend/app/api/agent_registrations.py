"""Admin listing of agent self-registration requests.

Surfaces registration rows created by the ungated bootstrap surface
(``api/internal_bootstrap.py``). Pending registrations are reviewed in the
Approvals inbox (``register_agent`` action type); this list endpoint remains
for history and debugging.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import CurrentUser, require_session
from ..db import read_session
from ..models import AgentRegistrationRequest
from ..schemas import AgentRegistrationListOut, AgentRegistrationOut

router = APIRouter(prefix="/api/v1/agent-registrations", tags=["agents"])


def _to_out(row: AgentRegistrationRequest) -> AgentRegistrationOut:
    return AgentRegistrationOut(
        id=row.id,
        requested_name=row.requested_name,
        description=row.description,
        rationale=row.rationale,
        client_hint=row.client_hint,
        status=row.status,
        agent_id=row.agent_id,
        permissions=json.loads(row.permissions) if row.permissions else None,
        created_at=row.created_at,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
        decision_reason=row.decision_reason,
        claimed_at=row.claimed_at,
        expires_at=row.expires_at,
    )


@router.get("", response_model=AgentRegistrationListOut)
async def list_registrations(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
    status: str | None = Query(default=None),
) -> AgentRegistrationListOut:
    stmt = select(AgentRegistrationRequest)
    if status:
        stmt = stmt.where(AgentRegistrationRequest.status == status)
    stmt = stmt.order_by(AgentRegistrationRequest.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return AgentRegistrationListOut(items=[_to_out(r) for r in rows])


__all__ = ["router"]
