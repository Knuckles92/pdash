"""Integration tests for the SSE endpoints."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request


@pytest.fixture(autouse=True)
def _reset_sse_starlette_exit_event() -> None:
    """sse_starlette caches a module-level anyio.Event bound to whatever loop
    first touched it. TestClient spins up a fresh loop per request, so the
    cached event leaks across tests with "bound to a different event loop"
    errors. Clear it before every test in this module.
    """
    from sse_starlette import sse as _sse_mod
    _sse_mod.AppStatus.should_exit_event = None
    _sse_mod.AppStatus.should_exit = False


# ---------------------------------------------------------------------------
# auth gates
# ---------------------------------------------------------------------------


def test_events_requires_session(client: TestClient) -> None:
    resp = client.get("/api/v1/events?topics=approvals")
    assert resp.status_code == 401


def test_events_requires_topics(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/events")
    assert resp.status_code == 400
    assert resp.json()["code"] == "events.topics_required"


def test_events_rejects_unknown_topic_prefix(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/v1/events?topics=garbage")
    assert resp.status_code == 400
    assert resp.json()["code"] == "events.unknown_topic"


def test_events_headers_forbid_proxy_transform(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SSE responses must carry ``no-transform`` so proxies (e.g. the Next.js
    rewrite proxy's gzip) don't buffer the stream — a compressed SSE stream
    delivers no events until the compressor flushes, i.e. never."""
    from app.api import events as events_mod

    # The real stream never ends; stub it so TestClient can drain the response.
    async def finite_stream(*args: object, **kwargs: object) -> AsyncGenerator[dict, None]:
        yield {"event": "ping", "data": "{}"}

    monkeypatch.setattr(events_mod, "_stream", finite_stream)
    resp = admin_client.get("/api/v1/events?topics=pages")
    assert resp.status_code == 200
    assert "no-transform" in resp.headers["cache-control"]
    assert resp.headers["x-accel-buffering"] == "no"


def test_internal_events_requires_service_secret(client: TestClient) -> None:
    # No Authorization header.
    resp = client.get("/api/v1/internal/events?topics=approvals")
    assert resp.status_code == 401


def test_internal_events_rejects_admin_topics(initialized_db, client: TestClient) -> None:
    """The MCP feed must not accept page/module/activity topics."""
    db_path, _ = initialized_db
    # Pull the service secret from kv_settings.
    import asyncio as _aio
    from app.auth.secrets import KEY_SERVICE_SECRET, get_kv
    from app.db import get_sessionmaker

    async def fetch_secret() -> str:
        sm = get_sessionmaker()
        async with sm() as s:
            return await get_kv(s, KEY_SERVICE_SECRET)

    secret = _aio.run(fetch_secret())
    resp = client.get(
        "/api/v1/internal/events?topics=page:pg_x",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "events.topic_not_allowed"


# ---------------------------------------------------------------------------
# happy path — replay
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Minimal ``Request`` stand-in for driving ``_stream`` directly.

    We do NOT exercise the SSE happy path through ``TestClient``: it runs the
    ASGI app to completion and buffers the entire body (see
    ``starlette/testclient.py``), so it cannot consume a long-lived stream, and
    its synthetic ``receive`` only yields ``http.disconnect`` *after* the
    response completes — a correct (non-terminating) stream would deadlock.
    ``_stream`` only touches ``request.is_disconnected()``, so a stub suffices.
    """

    async def is_disconnected(self) -> bool:
        return False


async def _collect(gen: AsyncGenerator[dict[str, str], None], count: int) -> list[dict[str, str]]:
    """Pull ``count`` SSE envelopes from ``gen`` then close it."""
    out: list[dict[str, str]] = []
    try:
        async for ev in gen:
            out.append(ev)
            if len(out) >= count:
                break
    finally:
        await gen.aclose()
    return out


async def test_stream_replays_since_last_event_id() -> None:
    """Events published before connect are replayed when ``last_event_id`` is
    older than them."""
    from app.api.events import _stream
    from app.events import bus

    bus.reset()
    bus.publish("approvals", "approval_pending", {"request_id": "a"})
    bus.publish("approvals", "approval_pending", {"request_id": "b"})

    gen = _stream({"approvals"}, 0, cast(Request, _FakeRequest()))
    events = await _collect(gen, count=2)
    payloads = [json.loads(e["data"]) for e in events]
    assert payloads[0]["payload"]["request_id"] == "a"
    assert payloads[1]["payload"]["request_id"] == "b"


async def test_stream_replay_miss_emits_resync_required() -> None:
    """If ``last_event_id`` predates the retained buffer, emit a single
    ``resync_required`` envelope and fall through to live."""
    from app.api.events import _stream
    from app.events import bus

    bus.reset()
    # Overflow the log_stream cap (500) so id=1 is evicted from the buffer.
    for i in range(550):
        bus.publish("log_stream:m1", "log_appended", {"i": i})

    gen = _stream({"log_stream:m1"}, 1, cast(Request, _FakeRequest()))
    events = await _collect(gen, count=1)
    assert events[0]["event"] == "resync_required"


async def test_stream_delivers_live_events_after_idle() -> None:
    """A live subscription must survive an idle window and still deliver events.

    Regression guard for the "stuck reconnecting" bug: the stream used to wrap
    ``__anext__`` in ``asyncio.wait_for(..., 1.0)``, which cancelled the pending
    get after 1s of idle; the bus read that cancellation as a disconnect and
    closed the subscription, so any event published after the first idle second
    was never delivered and the browser reconnect-looped forever.
    """
    from app.api.events import _stream
    from app.events import bus

    bus.reset()
    gen = _stream({"approvals"}, None, cast(Request, _FakeRequest()))

    collected: list[dict[str, str]] = []

    async def consume() -> None:
        async for ev in gen:
            collected.append(ev)
            break

    task = asyncio.ensure_future(consume())
    try:
        # Stay idle well past the old 1s self-cancel window before publishing.
        await asyncio.sleep(1.3)
        bus.publish("approvals", "approval_pending", {"request_id": "x"})
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        task.cancel()
        await gen.aclose()

    assert collected, "live event was not delivered after the idle window"
    assert json.loads(collected[0]["data"])["payload"]["request_id"] == "x"
