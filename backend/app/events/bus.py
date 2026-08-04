"""In-process pub/sub EventBus used by the SSE endpoints.

Design:

- A module-level singleton :class:`EventBus`. Initialised on app startup; no
  per-request setup. Lifecycle is process-wide.
- ``publish(topic, kind, payload)`` assigns a monotonically-increasing event
  id, appends to a per-topic ring buffer (5 min / 1000 events by default;
  ``log_stream:*`` topics get 1 min / 500; ``approvals`` gets 10 min / 2000),
  and ``put_nowait``s the event onto every registered subscriber queue for
  that topic.
- ``subscribe(topics)`` returns an :class:`AsyncIterator` over events, backed
  by an ``asyncio.Queue(maxsize=1000)``. The iterator cleans up its
  registration on cancellation (i.e. when the client disconnects).
- If a subscriber's queue is full when we try to publish to it, we drop the
  subscription by closing it with a ``kind: resync_required`` event and
  removing it from the registry. The publisher NEVER blocks.
- ``replay_since(topics, last_event_id)`` walks the ring buffers and returns
  events newer than ``last_event_id`` across the union of the requested
  topics, sorted by id. If the requested id is older than the oldest event
  still retained in any of those buffers, returns the string ``"miss"`` and
  the caller emits a single ``resync_required`` event.

This module is the single point of contention for write coordination — the
critical section is short (``put_nowait`` over a small set of queues), and
runs in the asyncio event loop on the same task that handled the HTTP
request, so we don't need any explicit locking.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from ..timefmt import utcnow_iso

logger = logging.getLogger(__name__)


# Ring buffer policy ---------------------------------------------------------

# (max_age_seconds, max_events)
_DEFAULT_POLICY: tuple[float, int] = (300.0, 1000)
_LOG_STREAM_POLICY: tuple[float, int] = (60.0, 500)
_APPROVALS_POLICY: tuple[float, int] = (600.0, 2000)


def _policy_for(topic: str) -> tuple[float, int]:
    if topic.startswith("log_stream:"):
        return _LOG_STREAM_POLICY
    if topic == "approvals":
        return _APPROVALS_POLICY
    return _DEFAULT_POLICY


# Event envelope -------------------------------------------------------------


@dataclass
class Event:
    """Wire envelope. Mirrors the SSE payload shape one-to-one."""

    id: int
    ts: str
    topic: str
    kind: str
    payload: dict[str, Any]

    def as_sse_dict(self) -> dict[str, Any]:
        return {
            "event": self.kind,
            "id": str(self.id),
            "data": json.dumps(
                {"topic": self.topic, "ts": self.ts, "payload": self.payload},
                separators=(",", ":"),
                default=str,
            ),
        }


# Subscriber tracking --------------------------------------------------------


@dataclass(eq=False)
class _Subscriber:
    id: int
    topics: frozenset[str]
    queue: asyncio.Queue[Event]
    closed: bool = False

    def __hash__(self) -> int:  # pragma: no cover - trivial
        return id(self)


class _Subscription:
    """Async-iterable that yields events from a registered subscriber.

    Returned by :meth:`EventBus.subscribe`. The subscriber is unregistered on
    iterator close (which the runtime triggers on GC and explicit
    ``aclose()`` calls; cancelling the consuming task also runs cleanup).
    """

    def __init__(self, bus: "EventBus", sub: _Subscriber) -> None:
        self._bus = bus
        self._sub = sub

    def __aiter__(self) -> "_Subscription":
        return self

    async def __anext__(self) -> Event:
        if self._sub.closed:
            raise StopAsyncIteration
        try:
            ev = await self._sub.queue.get()
        except asyncio.CancelledError:
            await self.aclose()
            raise
        if ev.kind == "resync_required":
            # The bus told us to bail. Hand this final event to the caller and
            # then stop.
            self._sub.closed = True
            return ev
        return ev

    async def aclose(self) -> None:
        if not self._sub.closed:
            self._sub.closed = True
            self._bus._unregister(self._sub)  # noqa: SLF001


# The bus itself ------------------------------------------------------------


class EventBus:
    """Singleton in-process event bus."""

    def __init__(self) -> None:
        self._counter = itertools.count(start=1)
        self._ring: dict[str, deque[tuple[float, Event]]] = {}
        # topic -> set of subscribers; a subscriber may live under multiple keys.
        self._subscribers: dict[str, set[_Subscriber]] = {}
        # subscriber registry by id (used for cleanup)
        self._sub_ids = itertools.count(start=1)

    # ---- helpers ----------------------------------------------------------

    def _next_event_id(self) -> int:
        return next(self._counter)

    @staticmethod
    def _mono() -> float:
        # ``time.monotonic`` works in any context (sync or async) — avoid
        # depending on a running event loop here, since publish() can be
        # called from sync hooks too.
        return time.monotonic()

    def _trim(self, topic: str) -> None:
        ring = self._ring.get(topic)
        if not ring:
            return
        max_age, max_count = _policy_for(topic)
        now = self._mono()
        # Trim by age (oldest first).
        while ring and (now - ring[0][0]) > max_age:
            ring.popleft()
        # Trim by count.
        while len(ring) > max_count:
            ring.popleft()

    # ---- publish ----------------------------------------------------------

    def publish(self, topic: str, kind: str, payload: dict[str, Any]) -> Event:
        """Append an event to the ring buffer for ``topic`` and fan out to subscribers.

        Never blocks. If a subscriber's queue is full, the subscriber is
        closed with a final ``resync_required`` envelope and removed from the
        topic registry.
        """
        event_id = self._next_event_id()
        ts = utcnow_iso()
        event = Event(id=event_id, ts=ts, topic=topic, kind=kind, payload=payload)

        # 1) Append to ring buffer.
        ring = self._ring.setdefault(topic, deque())
        ring.append((self._mono(), event))
        self._trim(topic)

        # 2) Fan out to subscribers.
        subs = list(self._subscribers.get(topic, ()))
        for sub in subs:
            if sub.closed:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "EventBus: subscriber %d full on topic %s — emitting "
                    "resync_required and dropping",
                    sub.id,
                    topic,
                )
                resync = Event(
                    id=self._next_event_id(),
                    ts=utcnow_iso(),
                    topic=topic,
                    kind="resync_required",
                    payload={"reason": "slow_subscriber", "topics": sorted(sub.topics)},
                )
                # Drop one item to make room, then enqueue the final
                # resync_required. We intentionally leave ``closed=False``: the
                # subscription iterator flips ``closed`` when it dequeues this
                # resync_required event, so the client still receives that last
                # event before the iterator stops.
                try:
                    _ = sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    sub.queue.put_nowait(resync)
                except asyncio.QueueFull:
                    pass
                self._unregister(sub)
        return event

    # ---- subscribe --------------------------------------------------------

    def _register(self, sub: _Subscriber) -> None:
        for topic in sub.topics:
            self._subscribers.setdefault(topic, set()).add(sub)

    def _unregister(self, sub: _Subscriber) -> None:
        for topic in sub.topics:
            bucket = self._subscribers.get(topic)
            if bucket is not None:
                bucket.discard(sub)
                if not bucket:
                    self._subscribers.pop(topic, None)

    def subscribe(self, topics: set[str]) -> "_Subscription":
        """Return an async-iterable subscription registered EAGERLY.

        Registration into the bus happens before the function returns, so the
        publisher can immediately fan events to the subscriber. The returned
        object is itself an ``async for``-able iterator; cancelling the
        consuming task causes its ``aclose`` to run and the subscriber to be
        unregistered.
        """
        if not topics:
            raise ValueError("subscribe: at least one topic required")
        sub = _Subscriber(
            id=next(self._sub_ids),
            topics=frozenset(topics),
            queue=asyncio.Queue(maxsize=1000),
        )
        self._register(sub)
        return _Subscription(self, sub)

    # ---- replay -----------------------------------------------------------

    def replay_since(
        self, topics: set[str], last_event_id: int
    ) -> list[Event] | str:
        """Return events newer than ``last_event_id`` across ``topics``.

        Returns the string ``"miss"`` if ``last_event_id`` is older than the
        oldest retained event in any of the requested topics (we can't be
        sure we didn't drop relevant events). The caller emits
        ``resync_required`` and the client refetches from REST.

        Returns an empty list if there is nothing newer — the caller starts a
        live subscription as normal.
        """
        if not topics:
            return []
        all_events: list[Event] = []
        for topic in topics:
            ring = self._ring.get(topic)
            if not ring:
                # Empty ring: treat as "no events for this topic since startup".
                continue
            oldest_id = ring[0][1].id
            if last_event_id < oldest_id - 1:
                # The caller already saw everything up to and including
                # oldest_id - 1, so seeing oldest_id next is contiguous (no
                # gap). Anything older than that means we evicted events the
                # caller hadn't seen yet — signal a miss.
                return "miss"
            for _ts, ev in ring:
                if ev.id > last_event_id:
                    all_events.append(ev)
        all_events.sort(key=lambda e: e.id)
        return all_events

    # ---- introspection (tests) -------------------------------------------

    def topic_size(self, topic: str) -> int:
        return len(self._ring.get(topic, ()))

    def subscriber_count(self, topic: str | None = None) -> int:
        if topic is None:
            seen: set[int] = set()
            for bucket in self._subscribers.values():
                for sub in bucket:
                    seen.add(sub.id)
            return len(seen)
        return len(self._subscribers.get(topic, ()))

    def reset(self) -> None:
        """Test hook. Clears all state."""
        self._counter = itertools.count(start=1)
        self._ring.clear()
        # Close every existing subscriber.
        for bucket in list(self._subscribers.values()):
            for sub in list(bucket):
                sub.closed = True
                try:
                    sub.queue.put_nowait(
                        Event(
                            id=0,
                            ts=utcnow_iso(),
                            topic="",
                            kind="resync_required",
                            payload={"reason": "bus_reset"},
                        )
                    )
                except asyncio.QueueFull:
                    pass
        self._subscribers.clear()
        self._sub_ids = itertools.count(start=1)


# Topic validation -----------------------------------------------------------

_KNOWN_PREFIXES = ("page:", "module:", "log_stream:", "agent:")
_KNOWN_SINGLETONS = {"approvals", "activity", "pages"}

_INTERNAL_ALLOWED_PREFIXES = ("agent:",)
_INTERNAL_ALLOWED_SINGLETONS = {"approvals"}


def _validate_topics(
    topics: list[str],
    *,
    allowed_prefixes: tuple[str, ...],
    allowed_singletons: set[str],
    reject_message: str,
) -> list[str]:
    """Validate ``topics`` against the given allow-lists; raise ValueError on the first bad one."""
    out: list[str] = []
    for t in topics:
        t = t.strip()
        if not t:
            continue
        if t in allowed_singletons:
            out.append(t)
            continue
        matched_prefix = next((p for p in allowed_prefixes if t.startswith(p)), None)
        if matched_prefix is not None:
            # Require a non-empty suffix after the prefix.
            if len(t) <= len(matched_prefix):
                raise ValueError(f"empty topic suffix: {t!r}")
            out.append(t)
            continue
        raise ValueError(f"{reject_message}: {t!r}")
    return out


def validate_topics(topics: list[str]) -> list[str]:
    """Validate a list of topic strings; raise ValueError on the first bad one."""
    return _validate_topics(
        topics,
        allowed_prefixes=_KNOWN_PREFIXES,
        allowed_singletons=_KNOWN_SINGLETONS,
        reject_message="unknown topic",
    )


def validate_internal_topics(topics: list[str]) -> list[str]:
    """Same as :func:`validate_topics` but restricted to MCP-server-allowed topics."""
    return _validate_topics(
        topics,
        allowed_prefixes=_INTERNAL_ALLOWED_PREFIXES,
        allowed_singletons=_INTERNAL_ALLOWED_SINGLETONS,
        reject_message="topic not allowed on internal feed",
    )


__all__ = [
    "Event",
    "EventBus",
    "validate_internal_topics",
    "validate_topics",
]
