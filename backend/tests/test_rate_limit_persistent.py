"""Tests for the persistent token-bucket rate limit (Phase 6).

The bucket lives in ``agent_rate_limits``. We hammer ``consume`` directly
to verify (a) buckets persist across calls/sessions, (b) refill works on
the wall clock, and (c) state is durable across reset_engine() (simulating
a restart).
"""

from __future__ import annotations

import asyncio
from pathlib import Path


def test_consume_persists_to_sqlite(initialized_db):
    """A consume() call should leave a row in agent_rate_limits."""
    from sqlalchemy import select

    from app.db import get_sessionmaker
    from app.models import AgentRateLimit
    from app.services.rate_limit import consume

    sm = get_sessionmaker()

    async def _go() -> tuple[bool, list[AgentRateLimit]]:
        allowed, _ = await consume("agt-rl-1", kind="write")
        async with sm() as session:
            rows = (
                await session.execute(
                    select(AgentRateLimit).where(
                        AgentRateLimit.agent_id == "agt-rl-1"
                    )
                )
            ).scalars().all()
        return allowed, list(rows)

    allowed, rows = asyncio.run(_go())
    assert allowed is True
    assert len(rows) == 1
    assert rows[0].action_class == "write"
    # After consuming 1, tokens should be capacity-1.
    assert 58.0 < rows[0].tokens < 60.0  # ~59 with tiny refill drift


def test_consume_writes_are_deducted_and_eventually_429(initialized_db):
    """Hammer until denied; verify the 60-token write cap."""
    from app.services.rate_limit import consume

    async def _go() -> tuple[int, float]:
        ok_count = 0
        retry_after = 0.0
        for _ in range(80):
            allowed, ra = await consume("hammer", kind="write")
            if allowed:
                ok_count += 1
            else:
                retry_after = ra
                break
        return ok_count, retry_after

    ok_count, retry_after = asyncio.run(_go())
    # Capacity is 60; expect 60 allowed then 429s with positive retry.
    assert 55 <= ok_count <= 60
    assert retry_after > 0.0


def test_read_and_write_buckets_are_independent(initialized_db):
    """A read-bucket exhaustion must not affect the write-bucket."""
    from app.services.rate_limit import consume

    async def _go() -> tuple[int, bool]:
        # Consume all write tokens.
        for _ in range(60):
            await consume("split-agent", kind="write")
        # Next write should be denied.
        write_allowed, _ = await consume("split-agent", kind="write")
        # But the read bucket is still full.
        read_allowed, _ = await consume("split-agent", kind="read")
        return 1 if write_allowed else 0, read_allowed

    write_after_60, read_allowed = asyncio.run(_go())
    assert write_after_60 == 0
    assert read_allowed is True


def test_consume_with_explicit_session_shares_transaction(initialized_db):
    """If a session is passed, the consume must not commit independently."""
    from sqlalchemy import select, text as sql_text

    from app.db import get_sessionmaker
    from app.models import AgentRateLimit
    from app.services.rate_limit import consume

    sm = get_sessionmaker()

    async def _go() -> int:
        async with sm() as session:
            await session.execute(sql_text("BEGIN IMMEDIATE"))
            await consume("txn-agent", kind="write", session=session)
            # Rollback: the bucket row should NOT have been persisted.
            await session.rollback()
        async with sm() as session:
            rows = (
                await session.execute(
                    select(AgentRateLimit).where(
                        AgentRateLimit.agent_id == "txn-agent"
                    )
                )
            ).scalars().all()
            return len(rows)

    n = asyncio.run(_go())
    assert n == 0


def test_persistence_survives_engine_reset(initialized_db):
    """Simulate a backend restart: rate-limit state must persist."""
    from sqlalchemy import select

    from app import db as dbmod
    from app.models import AgentRateLimit
    from app.services.rate_limit import consume, reset_all

    async def _phase1() -> float:
        await consume("survivor", kind="write")
        await consume("survivor", kind="write")
        async with dbmod.get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    select(AgentRateLimit).where(
                        AgentRateLimit.agent_id == "survivor"
                    )
                )
            ).scalars().all()
            return float(rows[0].tokens)

    pre_tokens = asyncio.run(_phase1())
    assert pre_tokens < 60.0

    # Simulate a fresh process: reset engine + in-mem cache.
    async def _phase2() -> float:
        await dbmod.reset_engine()
        reset_all()
        # Read the persisted tokens via a brand-new engine.
        async with dbmod.get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    select(AgentRateLimit).where(
                        AgentRateLimit.agent_id == "survivor"
                    )
                )
            ).scalars().all()
            return float(rows[0].tokens)

    post_tokens = asyncio.run(_phase2())
    # Tokens should not have reset to 60; they may have refilled slightly
    # due to wall-clock drift between the two phases.
    assert post_tokens < 60.0


def test_consume_unknown_kind_raises(initialized_db):
    from app.services.rate_limit import consume

    async def _go() -> str:
        try:
            await consume("x", kind="bogus")
        except ValueError as exc:
            return str(exc)
        return ""

    msg = asyncio.run(_go())
    assert "bogus" in msg


def test_rate_limit_via_internal_endpoint_returns_429(admin_client, initialized_db):
    """End-to-end: exhaust the write bucket, expect 429 + Retry-After."""
    from _phase3_helpers import (
        get_service_secret,
        home_page_id,
        internal_headers,
        register_agent,
    )

    agent_id, _ = register_agent(admin_client, name="rl-end2end")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)

    # Drain the write bucket directly via the service so we don't need 60
    # full HTTP rounds.
    from app.services.rate_limit import consume

    async def _drain() -> None:
        for _ in range(60):
            await consume(agent_id, kind="write")

    asyncio.run(_drain())

    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "x"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="rl-key"),
    )
    assert resp.status_code == 429, resp.text
    assert "Retry-After" in resp.headers
    body = resp.json()
    assert body.get("code") == "rate_limit.exceeded"
    assert body.get("retry_after_ms", 0) > 0
