"""Idempotency-Key helpers.

If the agent's tool call carries an ``idempotency_key`` argument, we forward
it verbatim to the backend. Otherwise the MCP server generates a key and
dedupes rapid retries by caching the chosen key per
``(agent_id, tool, args_hash)`` for ``idem_dedupe_ttl_s`` seconds.

This is a defense-in-depth measure: the backend's own
``request_idempotency`` table is the authoritative dedupe layer. The cache
here just makes "the agent called twice in 200ms while we were waiting on
the network" cost zero extra requests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass

from ulid import ULID

from .settings import get_settings


def _now() -> float:
    return time.monotonic()


@dataclass(frozen=True)
class _Entry:
    key: str
    expires_at: float


_cache: dict[tuple[str, str, str], _Entry] = {}
_lock = asyncio.Lock()


def new_key() -> str:
    """Generate a fresh ULID-based idempotency key."""
    return f"idem_{ULID()}"


def hash_args(args: dict) -> str:
    """Stable, order-insensitive hash of a JSON-serializable args dict."""
    blob = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def clear_cache() -> None:
    """Test hook."""
    _cache.clear()


def _purge_expired() -> None:
    cutoff = _now()
    for k in list(_cache.keys()):
        if _cache[k].expires_at <= cutoff:
            _cache.pop(k, None)


async def acquire(
    agent_id: str,
    tool: str,
    args: dict,
    supplied: str | None = None,
) -> str:
    """Return the idempotency key for this call.

    Logic:

    - If the caller supplied a key, use it verbatim (and do not cache —
      callers that care about dedupe are doing their own bookkeeping).
    - Otherwise, look up ``(agent_id, tool, args_hash)``; reuse the cached
      key if still alive, else mint a new one and cache.
    """
    if supplied:
        return supplied
    settings = get_settings()
    args_hash = hash_args(args)
    cache_k = (agent_id, tool, args_hash)
    async with _lock:
        _purge_expired()
        existing = _cache.get(cache_k)
        if existing is not None:
            return existing.key
        key = new_key()
        _cache[cache_k] = _Entry(key=key, expires_at=_now() + settings.idem_dedupe_ttl_s)
        return key
