"""Token-bucket rate limit per agent, persisted to SQLite.

Defaults: 60 writes/min, 600 reads/min. Buckets live in the
``agent_rate_limits`` table (migration 0003), so they survive process restarts
and stay consistent if multiple workers ever share a DB.

Two surface APIs:

- :func:`consume` (async, persistent) — used by the internal API routes.
- :func:`reset_all` (sync) — best-effort cache reset for test environments.
  The persistent rows are cleared per-test via the fresh-DB fixture.

Implementation notes:

- We hold an in-memory hint of the last bucket state to avoid re-reading from
  SQLite on the hot path, but every consume() also writes back. The DB is
  the source of truth; the in-memory copy is rebuilt on miss.
- The token refill uses wall-clock (ISO 8601) timestamps stored as TEXT so
  the value survives across processes. Per request we compute elapsed
  seconds via ``datetime.fromisoformat``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_sessionmaker
from ..timefmt import utcnow_iso

WRITES_PER_MINUTE = 60
READS_PER_MINUTE = 600

# Action-class -> (capacity, refill_per_sec).
_CONFIG: dict[str, tuple[float, float]] = {
    "write": (float(WRITES_PER_MINUTE), WRITES_PER_MINUTE / 60.0),
    "read": (float(READS_PER_MINUTE), READS_PER_MINUTE / 60.0),
}

# Process-local cache; cleared on reset_all().
_cache: dict[tuple[str, str], tuple[float, float]] = {}
_cache_lock = Lock()


def _parse_iso(s: str) -> datetime:
    # Tolerate the trailing 'Z' we use for compactness.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _refill(tokens: float, last_refill_iso: str, now: datetime, refill_per_sec: float, capacity: float) -> float:
    try:
        last = _parse_iso(last_refill_iso)
    except ValueError:
        return capacity  # safe default — start full
    elapsed = max(0.0, (now - last).total_seconds())
    return min(capacity, tokens + elapsed * refill_per_sec)


async def _consume_in_session(
    session: AsyncSession,
    agent_id: str,
    *,
    kind: str,
) -> tuple[bool, float]:
    """Internal helper: consume using the provided session.

    Used by :func:`consume` (which manages its own session and commit) and
    available to write endpoints that want to share a transaction with
    other writes.
    """
    if kind not in _CONFIG:
        raise ValueError(f"unknown kind {kind!r}")
    capacity, refill_per_sec = _CONFIG[kind]
    now_dt = datetime.now(UTC)
    now_iso = utcnow_iso()

    # Read current bucket (DB-first; in-memory is just a perf hint).
    row = (
        await session.execute(
            sql_text(
                "SELECT tokens, last_refill FROM agent_rate_limits "
                "WHERE agent_id = :aid AND action_class = :cls"
            ),
            {"aid": agent_id, "cls": kind},
        )
    ).first()
    if row is None:
        tokens = capacity
        last_refill_iso = now_iso
        is_new = True
    else:
        tokens = float(row[0])
        last_refill_iso = str(row[1])
        is_new = False

    tokens = _refill(tokens, last_refill_iso, now_dt, refill_per_sec, capacity)

    if tokens >= 1.0:
        tokens -= 1.0
        allowed = True
        retry_after = 0.0
    else:
        deficit = 1.0 - tokens
        retry_after = (
            deficit / refill_per_sec if refill_per_sec > 0 else 60.0
        )
        allowed = False

    # Persist.
    if is_new:
        await session.execute(
            sql_text(
                "INSERT INTO agent_rate_limits(agent_id, action_class, tokens, last_refill) "
                "VALUES (:aid, :cls, :tok, :ts)"
            ),
            {"aid": agent_id, "cls": kind, "tok": tokens, "ts": now_iso},
        )
    else:
        await session.execute(
            sql_text(
                "UPDATE agent_rate_limits SET tokens = :tok, last_refill = :ts "
                "WHERE agent_id = :aid AND action_class = :cls"
            ),
            {"aid": agent_id, "cls": kind, "tok": tokens, "ts": now_iso},
        )

    with _cache_lock:
        _cache[(agent_id, kind)] = (tokens, now_dt.timestamp())

    return allowed, retry_after


async def consume(
    agent_id: str,
    *,
    kind: str = "write",
    session: AsyncSession | None = None,
) -> tuple[bool, float]:
    """Try to consume one token. Returns ``(allowed, retry_after_seconds)``.

    If ``session`` is provided, the bucket read/write happens inside that
    transaction — the caller is responsible for commit/rollback. This is the
    fast path on write endpoints, which already hold a transaction via
    :func:`app.db.get_session`.

    If ``session`` is omitted, a short-lived session is opened, committed,
    and closed. Read-only endpoints that don't otherwise touch the DB use
    this form. SQLite is single-writer; this is fine for our admin-scale
    workload.
    """
    if session is not None:
        return await _consume_in_session(session, agent_id, kind=kind)
    sm = get_sessionmaker()
    async with sm() as own_session:
        await own_session.execute(sql_text("BEGIN IMMEDIATE"))
        try:
            result = await _consume_in_session(own_session, agent_id, kind=kind)
            await own_session.commit()
            return result
        except Exception:
            await own_session.rollback()
            raise


def reset_all() -> None:
    """Test helper: clear the in-memory cache.

    The persistent rows live in a per-test fresh DB, so this is mostly for
    paranoia: when a test reuses the engine but expects buckets reset.
    """
    with _cache_lock:
        _cache.clear()
