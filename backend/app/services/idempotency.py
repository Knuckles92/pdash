"""Idempotency-Key handling for admin POSTs.

For Phase 1, admin idempotency is keyed by ('user:admin', '<route>', '<key>').
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import RequestIdempotency, utcnow_iso


def read_idempotency_key(request: Request) -> str | None:
    """Read the ``Idempotency-Key`` request header (case-insensitive)."""
    return request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")


async def get_cached_response(
    session: AsyncSession,
    *,
    agent_id: str,
    tool: str,
    key: str,
) -> dict[str, Any] | None:
    row = await session.scalar(
        select(RequestIdempotency).where(
            RequestIdempotency.agent_id == agent_id,
            RequestIdempotency.tool == tool,
            RequestIdempotency.key == key,
        )
    )
    if row is None:
        return None
    try:
        return json.loads(row.response_snapshot)
    except json.JSONDecodeError:
        return None


async def store_response(
    session: AsyncSession,
    *,
    agent_id: str,
    tool: str,
    key: str,
    response: dict[str, Any],
    request_id: str | None = None,
) -> None:
    snapshot = json.dumps(response, separators=(",", ":"), default=str)
    row = RequestIdempotency(
        agent_id=agent_id,
        tool=tool,
        key=key,
        request_id=request_id,
        response_snapshot=snapshot,
        created_at=utcnow_iso(),
    )
    session.add(row)
    await session.flush()
