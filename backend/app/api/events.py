"""SSE endpoints (Phase 5).

Two routes:

- ``GET /api/v1/events`` — admin session, broad topic vocabulary.
- ``GET /api/v1/internal/events`` — service-secret auth, MCP-allowed topics
  only (``approvals`` + ``agent:<agent_id>``).

Wire format:

    id: 12345
    event: module_update
    data: {"topic":"page:pg_...","ts":"...","payload":{...}}

``sse_starlette.EventSourceResponse`` provides the keep-alive comment every
``ping=15`` seconds.

Replay: ``Last-Event-Id`` is sent by the browser EventSource on reconnect.
We accept either the HTTP header (browser default) or a ``?last_event_id=``
query parameter (handy for curl-based tests and the MCP server). If the bus
has lost the relevant range, we emit a single ``resync_required`` event and
fall through to live subscription — the client is responsible for refetching
the affected resource over REST.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..auth.deps import CurrentUser, require_session
from ..db import read_session
from ..errors import bad_request
from ..events import Event, bus, validate_internal_topics, validate_topics
from .internal_auth import _require_service_secret

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])

# ``no-transform`` stops intermediaries from compressing the stream. Without it
# the Next.js server's gzip (dev rewrite proxy and standalone alike) buffers the
# SSE stream indefinitely — the connection opens fine but no event ever reaches
# the browser. ``X-Accel-Buffering`` is the same opt-out for nginx-style proxies.
SSE_HEADERS = {
    "Cache-Control": "no-store, no-transform",
    "X-Accel-Buffering": "no",
}


def _parse_last_event_id(request: Request, override: str | None) -> int | None:
    raw = override or request.headers.get("last-event-id")
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_topics(csv: str | None) -> list[str]:
    if not csv:
        return []
    return [t.strip() for t in csv.split(",") if t.strip()]


async def _stream(
    topics: set[str],
    last_event_id: int | None,
    request: Request,
) -> AsyncGenerator[dict[str, str], None]:
    """Yield SSE envelopes (replay, then live)."""
    # 1) Replay if requested.
    if last_event_id is not None:
        replayed = bus.replay_since(topics, last_event_id)
        if isinstance(replayed, str):  # the sentinel "miss"
            # Emit a single resync_required envelope and switch to live.
            envelope = {
                "topic": "*",
                "ts": "",
                "payload": {"reason": "replay_miss", "topics": sorted(topics)},
            }
            yield {
                "event": "resync_required",
                "id": "0",
                "data": json.dumps(envelope, separators=(",", ":")),
            }
        else:
            for ev in replayed:
                yield ev.as_sse_dict()

    # 2) Live subscription.
    #
    # We poll ``request.is_disconnected()`` every second so the stream tears
    # down promptly when the client goes away. Crucially we must NOT use
    # ``asyncio.wait_for`` to bound the wait for the next event: ``wait_for``
    # *cancels* the pending ``__anext__`` on timeout, and the bus treats a
    # cancelled ``get`` as "consumer gone" and permanently closes the
    # subscription (see ``_Subscription.__anext__``). That closed the stream
    # after the very first idle second, so the browser reconnect-looped forever
    # (the stuck "reconnecting" pill). ``asyncio.wait`` lets the same pending
    # get survive across idle windows without cancelling it.
    sub = bus.subscribe(topics)
    nxt: asyncio.Task[Event] | None = None
    try:
        while True:
            if await request.is_disconnected():
                break
            if nxt is None:
                nxt = asyncio.ensure_future(sub.__anext__())
            done, _ = await asyncio.wait({nxt}, timeout=1.0)
            if nxt not in done:
                # Idle window elapsed; re-check disconnect, keep the same get.
                continue
            ev_task, nxt = nxt, None
            try:
                ev = ev_task.result()
            except StopAsyncIteration:
                break
            yield ev.as_sse_dict()
    finally:
        if nxt is not None:
            nxt.cancel()
        await sub.aclose()


# ---------------------------------------------------------------------------
# Admin endpoint
# ---------------------------------------------------------------------------


@router.get("/api/v1/events")
async def admin_events(
    request: Request,
    _: Annotated[CurrentUser, Depends(require_session)],
    topics: str | None = None,
    last_event_id: str | None = None,
) -> EventSourceResponse:
    """Admin SSE stream. Topics are a comma-separated list of channels.

    Example::

        GET /api/v1/events?topics=approvals,pages,page:pg_xxx
    """
    parsed = _parse_topics(topics)
    if not parsed:
        raise bad_request("events.topics_required", "topics= query param required")
    try:
        valid = validate_topics(parsed)
    except ValueError as exc:
        raise bad_request("events.unknown_topic", str(exc)) from exc
    last = _parse_last_event_id(request, last_event_id)
    gen = _stream(set(valid), last, request)
    return EventSourceResponse(gen, ping=15, headers=SSE_HEADERS)


# ---------------------------------------------------------------------------
# Internal endpoint (MCP-server feed; service secret only).
# ---------------------------------------------------------------------------


@router.get("/api/v1/internal/events")
async def internal_events(
    request: Request,
    session: Annotated[AsyncSession, Depends(read_session)],
    topics: str | None = None,
    last_event_id: str | None = None,
) -> EventSourceResponse:
    """MCP-server SSE stream.

    Auth is service-secret only (no ``X-Agent-Id`` is required here — this
    feed is consumed by the MCP server *process*, not on behalf of one agent).
    Allowed topics: ``approvals`` and optionally ``agent:<id>``.
    """
    await _require_service_secret(request, session)
    parsed = _parse_topics(topics)
    if not parsed:
        raise bad_request("events.topics_required", "topics= query param required")
    try:
        valid = validate_internal_topics(parsed)
    except ValueError as exc:
        raise bad_request("events.topic_not_allowed", str(exc)) from exc
    last = _parse_last_event_id(request, last_event_id)
    gen = _stream(set(valid), last, request)
    return EventSourceResponse(gen, ping=15, headers=SSE_HEADERS)


__all__ = ["router"]
