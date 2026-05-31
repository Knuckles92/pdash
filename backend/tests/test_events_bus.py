"""Unit tests for the in-process EventBus."""

from __future__ import annotations

import asyncio

import pytest

from app.events.bus import EventBus, validate_internal_topics, validate_topics


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


# ---------------------------------------------------------------------------
# basic publish/subscribe
# ---------------------------------------------------------------------------


async def test_publish_subscribe_basic(bus: EventBus) -> None:
    received: list = []

    async def consumer() -> None:
        async for ev in bus.subscribe({"approvals"}):
            received.append(ev)
            if len(received) >= 2:
                return

    task = asyncio.create_task(consumer())
    # Give the subscriber a tick to register.
    await asyncio.sleep(0)
    bus.publish("approvals", "approval_pending", {"request_id": "a"})
    bus.publish("approvals", "approval_pending", {"request_id": "b"})
    await asyncio.wait_for(task, timeout=1.0)

    assert [e.payload["request_id"] for e in received] == ["a", "b"]
    assert received[0].topic == "approvals"
    assert received[0].kind == "approval_pending"
    assert received[0].id < received[1].id


async def test_ring_buffer_trimming(bus: EventBus) -> None:
    # log_stream policy is 500 events. Publish 600 — only the last 500 stay.
    topic = "log_stream:mod_x"
    for i in range(600):
        bus.publish(topic, "log_appended", {"i": i})
    assert bus.topic_size(topic) == 500


async def test_replay_since_hit(bus: EventBus) -> None:
    for i in range(5):
        bus.publish("approvals", "approval_pending", {"i": i})
    replayed = bus.replay_since({"approvals"}, last_event_id=2)
    assert replayed != "miss"
    assert [ev.payload["i"] for ev in replayed] == [2, 3, 4]


async def test_replay_since_miss(bus: EventBus) -> None:
    # Force a tiny buffer by publishing > policy.max_count on log_stream.
    for i in range(550):
        bus.publish("log_stream:abc", "log_appended", {"i": i})
    # The first ~50 events have been evicted. last_event_id=1 should miss.
    result = bus.replay_since({"log_stream:abc"}, last_event_id=1)
    assert result == "miss"


async def test_replay_since_empty_topic_returns_empty(bus: EventBus) -> None:
    # Caller asks for replay on an empty topic — we return [], not "miss".
    result = bus.replay_since({"approvals"}, last_event_id=0)
    assert result == []


async def test_full_queue_closes_slow_subscriber(bus: EventBus) -> None:
    """If a subscriber's queue fills up, the bus drops it via resync_required."""
    # Build a subscriber that never reads; subscribe registers eagerly.
    sub = bus.subscribe({"approvals"})
    # Fill the underlying queue. We can publish 1000 events to do it.
    for i in range(1000):
        bus.publish("approvals", "approval_pending", {"i": i})
    # The 1001st publish should overflow and trigger the drop.
    bus.publish("approvals", "approval_pending", {"i": "overflow"})
    # After the overflow, the slow subscriber is removed from the registry.
    assert bus.subscriber_count("approvals") == 0
    # Draining the subscriber's iterator: at some point we should see a
    # ``resync_required`` envelope and then the iterator stops.
    received_kinds: list[str] = []
    async def drain() -> None:
        async for ev in sub:
            received_kinds.append(ev.kind)
            if ev.kind == "resync_required":
                return
    await asyncio.wait_for(drain(), timeout=1.0)
    assert "resync_required" in received_kinds


# ---------------------------------------------------------------------------
# topic validation
# ---------------------------------------------------------------------------


def test_validate_topics_accepts_known() -> None:
    out = validate_topics(["approvals", "pages", "activity", "page:pg_x", "module:mod_x", "log_stream:mod_x"])
    assert "approvals" in out
    assert "page:pg_x" in out


def test_validate_topics_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        validate_topics(["not_a_topic"])


def test_validate_topics_rejects_empty_suffix() -> None:
    with pytest.raises(ValueError):
        validate_topics(["page:"])


def test_validate_internal_topics_restricts() -> None:
    # MCP feed accepts approvals + agent:<id>.
    out = validate_internal_topics(["approvals", "agent:agt_x"])
    assert "approvals" in out
    assert "agent:agt_x" in out


def test_validate_internal_topics_rejects_page_topic() -> None:
    with pytest.raises(ValueError):
        validate_internal_topics(["page:pg_x"])


# ---------------------------------------------------------------------------
# subscription cleanup
# ---------------------------------------------------------------------------


async def test_subscriber_cleans_up_on_cancel(bus: EventBus) -> None:
    async def consumer() -> None:
        async for _ in bus.subscribe({"approvals"}):
            await asyncio.sleep(10)  # block forever — the test will cancel us.

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)
    assert bus.subscriber_count("approvals") == 1
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # Give the finally-clause a tick.
    await asyncio.sleep(0)
    assert bus.subscriber_count("approvals") == 0
