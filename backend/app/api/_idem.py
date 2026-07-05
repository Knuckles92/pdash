"""Idempotency-Key handling helper for admin routes.

The pattern: a POST route inspects the `Idempotency-Key` header; if a cached
response exists, return it directly with `X-Idempotency-Replay: true`. Otherwise
execute the handler and persist the response.

For Phase 1, admin idempotency uses agent_id='user:admin'.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.idempotency import get_cached_response, read_idempotency_key, store_response

ADMIN_AGENT_KEY = "user:admin"


def header(request: Request) -> str | None:
    return read_idempotency_key(request)


async def lookup(
    session: AsyncSession, *, tool: str, key: str | None
) -> dict[str, Any] | None:
    if not key:
        return None
    return await get_cached_response(
        session, agent_id=ADMIN_AGENT_KEY, tool=tool, key=key
    )


async def save(
    session: AsyncSession,
    *,
    tool: str,
    key: str | None,
    response: dict[str, Any],
) -> None:
    if not key:
        return
    await store_response(
        session,
        agent_id=ADMIN_AGENT_KEY,
        tool=tool,
        key=key,
        response=response,
    )
