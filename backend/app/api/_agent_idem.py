"""Idempotency-Key handling for the ``/internal/*`` surface.

Scope is ``(agent_id, tool, key)``. Returns the cached
response dict with the original ``status_code``; the calling route sets the
``X-Idempotency-Replay: true`` header.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ProblemDetail
from ..services.idempotency import get_cached_response, read_idempotency_key, store_response


def header(request: Request) -> str | None:
    return read_idempotency_key(request)


def require_header(request: Request) -> str:
    """Idempotency-Key is required on internal POSTs."""
    key = header(request)
    if not key:
        raise ProblemDetail(
            status=400,
            code="idempotency.required",
            title="Bad Request",
            detail="Idempotency-Key header is required on internal POSTs",
        )
    return key


async def lookup(
    session: AsyncSession, *, agent_id: str, tool: str, key: str
) -> dict[str, Any] | None:
    return await get_cached_response(session, agent_id=agent_id, tool=tool, key=key)


async def save(
    session: AsyncSession,
    *,
    agent_id: str,
    tool: str,
    key: str,
    response: dict[str, Any],
    request_id: str | None = None,
) -> None:
    await store_response(
        session,
        agent_id=agent_id,
        tool=tool,
        key=key,
        response=response,
        request_id=request_id,
    )
