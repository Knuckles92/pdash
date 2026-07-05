"""Ungated agent self-registration ("bootstrap") surface.

A new AI client connects to the MCP server with NO agent key. The MCP server
forwards its registration request here using only the shared service secret
(no ``X-Agent-Id`` — there is no agent yet), exactly like ``/resolve-key``.

Flow:

1. ``POST /register`` — create a ``pending`` registration; return a one-time
   claim token. **Never** mints a key (admin must approve first).
2. Admin approves/denies in the Approvals inbox (``register_agent`` action type).
3. ``POST /claim`` — the client polls with its claim token. While pending it
   gets ``status='pending'``; once approved the key is minted *on this call*
   (mint-on-claim) and returned exactly once, then the request is ``claimed``.

This keeps every other MCP tool gated behind a real ``hb_agt_`` key while making
first contact possible without one, and keeps registration admin-controlled.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..errors import ProblemDetail, conflict, not_found
from ..ids import new_id
from ..approval import lifecycle
from ..approval.orchestrator import submit_request
from ..models import Agent, AgentRegistrationRequest, ApprovalRequest, utcnow_iso
from ..schemas import (
    BootstrapClaimIn,
    BootstrapClaimOut,
    BootstrapRegisterIn,
    BootstrapRegisterOut,
)
from ..services.agent_keys import generate_agent_api_key
from ..services.agent_registration import expires_in, generate_claim_token, hash_claim_token
from ..services.audit import write_event
from .internal_auth import _require_service_secret

router = APIRouter(prefix="/api/v1/internal/bootstrap", tags=["internal"])


async def _expire_stale(session: AsyncSession, now: str) -> None:
    """Demote pending/approved-but-unclaimed requests past their TTL to 'expired'.

    Expiry is otherwise lazy (only the polled token flips in ``/claim``); doing it
    here keeps the queue cap, the duplicate-name check, and the admin queue honest
    without a background sweeper. Linked ``register_agent`` approval rows are
    expired in the same pass.
    """
    stale_ids = (
        await session.execute(
            select(AgentRegistrationRequest.id).where(
                AgentRegistrationRequest.status.in_(("pending", "approved")),
                AgentRegistrationRequest.expires_at.is_not(None),
                AgentRegistrationRequest.expires_at < now,
            )
        )
    ).scalars().all()
    if not stale_ids:
        return
    await session.execute(
        update(AgentRegistrationRequest)
        .where(AgentRegistrationRequest.id.in_(stale_ids))
        .values(status="expired")
    )
    apr_rows = (
        await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.action_type == "register_agent",
                ApprovalRequest.status == "pending",
                ApprovalRequest.target_id.in_(stale_ids),
            )
        )
    ).scalars().all()
    for apr in apr_rows:
        lifecycle.mark_expired(apr, reason="ttl")


@router.post("/register", response_model=BootstrapRegisterOut, status_code=201)
async def register_request(
    body: BootstrapRegisterIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BootstrapRegisterOut:
    """Create a pending agent-registration request. Auth: service secret only."""
    await _require_service_secret(request, session)
    settings = get_settings()
    now = utcnow_iso()
    await _expire_stale(session, now)

    # Bound the ungated path: cap how many requests can sit unapproved so a
    # keyless caller can't flood the admin's approval queue.
    pending = await session.scalar(
        select(func.count())
        .select_from(AgentRegistrationRequest)
        .where(AgentRegistrationRequest.status == "pending")
    )
    if pending is not None and pending >= settings.agent_registration_max_pending:
        raise ProblemDetail(
            status=429,
            code="registration.queue_full",
            title="Too Many Requests",
            detail=(
                "Too many agent registrations are awaiting admin approval. Ask "
                "the admin to review the pending queue, then try again."
            ),
        )

    # display_name is globally unique on agents; reject a clash up front so the
    # client picks a free name. (This intentionally signals name availability on
    # the ungated path — harmless on a single-admin tailnet.) Also reject a name
    # already awaiting approval/claim so duplicates can't accumulate and dead-end.
    if await session.scalar(select(Agent).where(Agent.display_name == body.display_name)):
        raise conflict(
            "agent.name_taken",
            f"An agent named {body.display_name!r} already exists; choose another name.",
        )
    live_dupe = await session.scalar(
        select(AgentRegistrationRequest).where(
            AgentRegistrationRequest.requested_name == body.display_name,
            AgentRegistrationRequest.status.in_(("pending", "approved")),
        )
    )
    if live_dupe is not None:
        raise conflict(
            "registration.name_pending",
            f"A registration for {body.display_name!r} is already awaiting approval "
            "or pickup; choose another name or wait for it to be decided.",
        )

    token, token_hash = generate_claim_token()
    rid = new_id("areg")
    expires_at = expires_in(settings.agent_registration_ttl_seconds)
    row = AgentRegistrationRequest(
        id=rid,
        requested_name=body.display_name,
        description=body.description,
        rationale=body.rationale,
        client_hint=body.client_hint,
        status="pending",
        claim_token_hash=token_hash,
        created_at=now,
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()

    proposed_payload = {
        "display_name": body.display_name,
        "description": body.description,
        "rationale": body.rationale,
        "client_hint": body.client_hint,
    }
    await submit_request(
        session,
        agent_id=None,
        action_type="register_agent",
        target_kind="agent_registration",
        target_id=rid,
        proposed_payload=proposed_payload,
    )

    return BootstrapRegisterOut(
        registration_id=rid,
        claim_token=token,
        status="pending",
        expires_at=expires_at,
    )


@router.post("/claim", response_model=BootstrapClaimOut)
async def claim_request(
    body: BootstrapClaimIn,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BootstrapClaimOut:
    """Poll a registration; mint + return the key once on the first approved poll.

    Auth: service secret only. The claim token (not an agent key) authenticates
    the caller to its own registration.
    """
    await _require_service_secret(request, session)

    token_hash = hash_claim_token(body.claim_token)
    row = await session.scalar(
        select(AgentRegistrationRequest).where(
            AgentRegistrationRequest.claim_token_hash == token_hash
        )
    )
    if row is None or (body.registration_id and body.registration_id != row.id):
        raise not_found("registration.not_found", "registration")

    now = utcnow_iso()
    # Lazily expire a stale request on read — both pending and approved-but-unclaimed
    # rows have a bounded claim window, so neither mints a key past its TTL.
    if row.status in ("pending", "approved") and row.expires_at and row.expires_at < now:
        row.status = "expired"
        await session.flush()

    if row.status == "pending":
        return BootstrapClaimOut(
            status="pending", registration_id=row.id, expires_at=row.expires_at
        )
    if row.status == "denied":
        return BootstrapClaimOut(
            status="denied", registration_id=row.id, reason=row.decision_reason
        )
    if row.status == "expired":
        return BootstrapClaimOut(status="expired", registration_id=row.id)
    if row.status == "claimed":
        # The key was revealed once already; never re-issue it.
        return BootstrapClaimOut(
            status="claimed",
            registration_id=row.id,
            agent_id=row.agent_id,
            display_name=row.requested_name,
        )

    # status == 'approved' -> mint the agent + key now, exactly once.
    clash = await session.scalar(
        select(Agent).where(Agent.display_name == row.requested_name)
    )
    if clash is not None:
        raise conflict(
            "agent.name_taken",
            f"An agent named {row.requested_name!r} now exists; ask the admin to deny "
            "this registration, then request again under a different name.",
        )

    plaintext, hashed = generate_agent_api_key()
    aid = new_id("agt")
    agent = Agent(
        id=aid,
        display_name=row.requested_name,
        description=row.description,
        api_key_hash=hashed,
        permissions=row.permissions or "{}",
        status="active",
        created_at=now,
        last_key_rotated_at=now,
    )
    session.add(agent)
    row.status = "claimed"
    row.agent_id = aid
    row.claimed_at = now
    await session.flush()

    # Audit the mint, but never log the plaintext key.
    await write_event(
        session,
        actor_kind="system",
        actor_id=None,
        action_type="agent_registration_claimed",
        target_kind="agent",
        target_id=aid,
        outcome="applied",
        payload_summary={"display_name": row.requested_name, "registration_id": row.id},
    )

    return BootstrapClaimOut(
        status="approved",
        registration_id=row.id,
        api_key=plaintext,
        agent_id=aid,
        display_name=row.requested_name,
    )


__all__ = ["router"]
