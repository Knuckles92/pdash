"""Per-agent decision cache backed by an SSE subscription (Phase 5).

A persistent SSE consumer streams ``approvals`` events from the backend
``/api/v1/internal/events?topics=approvals`` and updates an in-process map
``{request_id -> request_snapshot}`` keyed by ``agent_id`` for each event it
sees. ``status_of(agent_id, request_id)`` answers from the cache without
round-tripping the backend.

The subscription task starts on FastMCP app startup (see
``app.main.main``) and is cancelled on shutdown. If the SSE stream drops,
we reconnect using the last-seen event id; on ``resync_required`` we
flush the cache and let the next ``status_of`` call refresh on demand.

When a write tool returns ``pending``, the tool layer calls
:func:`note_pending` so the cache contains the request even if the event
hasn't arrived yet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .backend import BackendError, get_client

logger = logging.getLogger(__name__)

# Fallback freshness budget for stale cache reads when no SSE event has
# touched the agent yet. Phase 3 used a 5s read-through; Phase 5 lowers it
# because the SSE stream typically delivers in <1s.
_STALE_S: float = 30.0


@dataclass
class _AgentCache:
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    fetched_at: float = 0.0
    needs_resync: bool = False


_cache: dict[str, _AgentCache] = {}
_lock = asyncio.Lock()

# Track the highest event id we've delivered, so reconnects resume.
_last_event_id: int = 0

# Whether the SSE consumer is currently believed connected.
_sse_connected: bool = False

# Background task handle (set by start_subscription / cleared by stop_subscription).
_task: asyncio.Task | None = None
_stop_evt: asyncio.Event | None = None


def _now() -> float:
    return time.monotonic()


def clear_cache() -> None:
    """Test hook — clears state and forces the next refresh."""
    global _last_event_id, _sse_connected
    _cache.clear()
    _last_event_id = 0
    _sse_connected = False


# ---------------------------------------------------------------------------
# Public read path
# ---------------------------------------------------------------------------


async def status_of(agent_id: str, request_id: str) -> dict[str, Any] | None:
    """Look up the cached status of ``request_id`` for ``agent_id``.

    Falls back to a REST refresh if the cache says ``needs_resync`` or has
    never been hydrated within the freshness window. Returns ``None`` if the
    request is not visible to the cache after best-effort lookup.
    """
    async with _lock:
        agent_cache = _cache.get(agent_id)
        if (
            agent_cache is not None
            and request_id in agent_cache.entries
            and not agent_cache.needs_resync
        ):
            return agent_cache.entries[request_id]
        if (
            agent_cache is not None
            and not agent_cache.needs_resync
            and (_now() - agent_cache.fetched_at) < _STALE_S
        ):
            return agent_cache.entries.get(request_id)

    # Refresh from the read endpoint.
    try:
        body = await get_client().list_my_pending_requests(
            agent_id,
            status_filter="pending,approved,denied,applied,application_failed,superseded,expired",
            limit=200,
        )
    except BackendError:
        async with _lock:
            agent_cache = _cache.get(agent_id)
            return agent_cache.entries.get(request_id) if agent_cache is not None else None

    async with _lock:
        agent_cache = _cache.setdefault(agent_id, _AgentCache())
        for request_row in body.get("items", []):
            agent_cache.entries[request_row["id"]] = request_row
        agent_cache.fetched_at = _now()
        agent_cache.needs_resync = False
        return agent_cache.entries.get(request_id)


async def note_pending(agent_id: str, request: dict[str, Any]) -> None:
    """Insert a freshly-issued pending request into the cache.

    Tools call this immediately after a write returns pending so that any
    subsequent ``status_of`` (e.g. via ``list_my_pending_requests``) sees it
    even if the SSE event hasn't been delivered yet.
    """
    async with _lock:
        agent_cache = _cache.setdefault(agent_id, _AgentCache())
        agent_cache.entries[request["id"]] = request


# ---------------------------------------------------------------------------
# SSE subscription
# ---------------------------------------------------------------------------


def is_connected() -> bool:
    return _sse_connected


def last_event_id() -> int:
    return _last_event_id


async def _apply_event(payload: dict[str, Any]) -> None:
    """Update the cache from a single decoded ``approval_*`` event payload."""
    agent_id = payload.get("agent_id")
    request_id = payload.get("request_id")
    if not agent_id or not request_id:
        return
    async with _lock:
        agent_cache = _cache.setdefault(agent_id, _AgentCache())
        existing = agent_cache.entries.get(request_id, {})
        existing.update(payload)
        # Synthesise status from event:
        # - approval_pending → status=pending
        # - approval_decided + outcome=applied → status=applied
        # - approval_decided + outcome=denied → status=denied
        outcome = payload.get("outcome")
        if outcome:
            if outcome == "applied":
                existing["status"] = "applied"
            elif outcome == "denied":
                existing["status"] = "denied"
            elif outcome == "application_failed":
                existing["status"] = "application_failed"
        elif "expires_at" in payload and "outcome" not in payload:
            existing["status"] = "pending"
        existing["id"] = request_id
        agent_cache.entries[request_id] = existing
        agent_cache.fetched_at = _now()


def _parse_sse_line_block(block: str) -> tuple[str | None, int | None, dict[str, Any] | None]:
    """Parse one SSE event block (delimited by blank line) into (event, id, data dict).

    Lines may be field-only or field: value. The ``data:`` line is JSON.
    Comments (lines starting with ":") are skipped.
    """
    event: str | None = None
    event_id: int | None = None
    data: str | None = None
    for line in block.splitlines():
        if not line:
            continue
        if line.startswith(":"):
            continue
        if ":" not in line:
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
        elif field == "id":
            try:
                event_id = int(value)
            except ValueError:
                event_id = None
        elif field == "data":
            data = (data + "\n" + value) if data else value
    if data is None:
        return event, event_id, None
    try:
        return event, event_id, json.loads(data)
    except json.JSONDecodeError:
        return event, event_id, None


async def _consume_stream(stop_evt: asyncio.Event) -> None:
    """Run the SSE consumer loop until ``stop_evt`` is set."""
    global _last_event_id, _sse_connected

    # Pick up the *current* BackendClient configuration so tests that point
    # the client at a live ephemeral backend share the same URL + secret.
    url, base_headers = get_client().sse_stream_request()

    while not stop_evt.is_set():
        headers = dict(base_headers)
        if _last_event_id:
            headers["Last-Event-Id"] = str(_last_event_id)
        params = {"topics": "approvals"}
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "GET", url, headers=headers, params=params
                ) as resp:
                    if resp.status_code != 200:
                        logger.warning(
                            "decision_cache SSE got HTTP %s; will retry",
                            resp.status_code,
                        )
                        raise httpx.HTTPError(f"sse status {resp.status_code}")
                    _sse_connected = True
                    pending_text = ""
                    async for chunk in resp.aiter_text():
                        if stop_evt.is_set():
                            break
                        pending_text += chunk
                        while "\n\n" in pending_text:
                            block, pending_text = pending_text.split("\n\n", 1)
                            event, event_id, data = _parse_sse_line_block(block)
                            if event_id is not None and event_id > _last_event_id:
                                _last_event_id = event_id
                            if data is None:
                                continue
                            payload = data.get("payload") or {}
                            if event == "resync_required":
                                async with _lock:
                                    for agent_cache in _cache.values():
                                        agent_cache.needs_resync = True
                                continue
                            await _apply_event(payload)
        except (httpx.HTTPError, OSError) as exc:
            logger.info("decision_cache SSE disconnected: %s", exc)
        finally:
            _sse_connected = False
        if stop_evt.is_set():
            break
        # Backoff before reconnect.
        try:
            await asyncio.wait_for(stop_evt.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


def start_subscription() -> None:
    """Start the background SSE subscriber. Idempotent."""
    global _task, _stop_evt
    if _task is not None and not _task.done():
        return
    _stop_evt = asyncio.Event()
    _task = asyncio.create_task(_consume_stream(_stop_evt), name="decision_cache_sse")
    logger.info("decision_cache SSE subscriber started")


async def stop_subscription() -> None:
    """Cancel the background SSE subscriber and await its cleanup."""
    global _task, _stop_evt
    if _task is None:
        return
    if _stop_evt is not None:
        _stop_evt.set()
    _task.cancel()
    try:
        await asyncio.wait_for(_task, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    _task = None
    _stop_evt = None
    logger.info("decision_cache SSE subscriber stopped")


__all__ = [
    "clear_cache",
    "is_connected",
    "last_event_id",
    "note_pending",
    "start_subscription",
    "status_of",
    "stop_subscription",
]
