"""Claim tokens for agent self-registration.

A keyless client that requests registration gets back a one-time *claim token*
(distinct from any agent API key). It polls ``/claim`` with this token; once the
admin approves, that endpoint mints the real ``hb_agt_`` key and returns it once.

Only the sha256 of the claim token is persisted (``claim_token_hash``) so a DB
leak never exposes a live token. The token is high-entropy (256 bits) so a plain
hash lookup is safe — no per-row argon2 scan like agent keys need.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..errors import conflict
from ..models import Agent, AgentRegistrationRequest, ApprovalRequest, utcnow_iso
from ..timefmt import iso_millis

CLAIM_TOKEN_PREFIX = "hb_reg_"


def expires_in(seconds: int) -> str:
    """ISO-8601 UTC timestamp ``seconds`` from now (the claim window deadline)."""
    return iso_millis(datetime.now(UTC) + timedelta(seconds=seconds))


def hash_claim_token(token: str) -> str:
    """Return the sha256 hex digest stored for a claim token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_claim_token() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hash)``.

    The plaintext (``hb_reg_<base32>``) is returned to the requesting client
    exactly once; only the hash is stored.
    """
    raw = secrets.token_bytes(32)
    encoded = base64.b32encode(raw).rstrip(b"=").decode("ascii").lower()
    token = f"{CLAIM_TOKEN_PREFIX}{encoded}"
    return token, hash_claim_token(token)


async def approve_registration_row(
    session: AsyncSession,
    row: AgentRegistrationRequest,
    *,
    decided_by: str,
    display_name: str | None = None,
    description: str | None = None,
    permissions: dict[str, Any] | None = None,
) -> None:
    """Mark a pending registration approved and refresh its claim window."""
    now = utcnow_iso()
    if row.expires_at and row.expires_at < now:
        raise conflict(
            "registration.expired",
            "This registration has expired; ask the agent to request again.",
        )
    name = (display_name or row.requested_name).strip()
    if not name:
        raise conflict("registration.invalid_name", "display_name cannot be empty")
    clash = await session.scalar(select(Agent).where(Agent.display_name == name))
    if clash is not None:
        raise conflict(
            "agent.name_taken",
            f"An agent named {name!r} already exists; pick another name.",
        )
    row.requested_name = name
    if description is not None:
        row.description = description
    if permissions is not None:
        row.permissions = json.dumps(permissions)
    row.status = "approved"
    row.decided_at = now
    row.decided_by = decided_by
    row.expires_at = expires_in(get_settings().agent_registration_ttl_seconds)
    await session.flush()


async def deny_registration_row(
    session: AsyncSession,
    row: AgentRegistrationRequest,
    *,
    decided_by: str,
    reason: str | None = None,
    allow_approved: bool = False,
) -> None:
    """Deny a registration. Optionally allow denying approved-but-unclaimed rows."""
    if row.status == "pending":
        pass
    elif allow_approved and row.status == "approved":
        pass
    else:
        raise conflict(
            "registration.not_decidable",
            f"registration is {row.status!r}",
        )
    row.status = "denied"
    row.decided_at = utcnow_iso()
    row.decided_by = decided_by
    row.decision_reason = reason
    await session.flush()


async def expire_registration_row(
    session: AsyncSession,
    row: AgentRegistrationRequest,
) -> None:
    """Demote a pending/approved-but-unclaimed registration to expired."""
    if row.status in ("pending", "approved"):
        row.status = "expired"
        await session.flush()


async def sync_registration_denied_from_approval(
    session: AsyncSession,
    request: ApprovalRequest,
    *,
    decided_by: str,
    reason: str | None = None,
) -> None:
    """When a register_agent approval is denied, mirror the decision on the registration."""
    if request.action_type != "register_agent":
        return
    if request.target_kind != "agent_registration" or not request.target_id:
        return
    row = await session.get(AgentRegistrationRequest, request.target_id)
    if row is None:
        return
    if row.status in ("pending", "approved"):
        await deny_registration_row(
            session,
            row,
            decided_by=decided_by,
            reason=reason,
            allow_approved=True,
        )


__all__ = [
    "CLAIM_TOKEN_PREFIX",
    "approve_registration_row",
    "deny_registration_row",
    "expire_registration_row",
    "expires_in",
    "generate_claim_token",
    "hash_claim_token",
    "sync_registration_denied_from_approval",
]
