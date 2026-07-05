"""Per-request agent resolution from the MCP HTTP request.

The MCP client sets ``Authorization: Bearer hb_agt_<...>`` on its requests
to the MCP server (the transport carries it through the streamable-HTTP
binding). For each incoming tool call we extract the key, resolve it to an
agent via the backend's ``/api/v1/internal/auth/resolve-key``, and stash the
:class:`AgentInfo` on a context dictionary keyed by the MCP request id.

Resolved entries are cached for ``auth_cache_ttl_s`` (default 30s) so
repeated tool calls in the same agent session don't hammer argon2.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .backend import AgentInfo, get_client
from .settings import get_settings

if TYPE_CHECKING:
    from starlette.requests import Request


@dataclass(frozen=True)
class _CacheEntry:
    info: AgentInfo
    expires_at: float


class AuthError(Exception):
    """Raised for missing/invalid bearer tokens."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_cache: dict[str, _CacheEntry] = {}
_cache_lock = asyncio.Lock()


def _now() -> float:
    return time.monotonic()


def _purge_expired() -> None:
    cutoff = _now()
    for k in list(_cache.keys()):
        if _cache[k].expires_at <= cutoff:
            _cache.pop(k, None)


def clear_cache() -> None:
    """Test hook."""
    _cache.clear()


def extract_bearer(request: "Request | None") -> str | None:
    """Pull the ``hb_agt_...`` bearer token from a Starlette request."""
    if request is None:
        return None
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    return token or None


async def resolve_from_request(request: "Request | None") -> AgentInfo:
    """Extract the agent from the MCP request's Authorization header.

    Raises :class:`AuthError` on missing/invalid keys.
    """
    token = extract_bearer(request)
    if not token:
        raise AuthError("auth.missing", "Missing Authorization: Bearer <agent_key>")
    return await resolve_token(token)


async def resolve_token(token: str) -> AgentInfo:
    settings = get_settings()
    async with _cache_lock:
        _purge_expired()
        cached = _cache.get(token)
        if cached is not None:
            return cached.info
    info = await get_client().resolve_key(token)
    if info is None:
        raise AuthError("auth.invalid", "API key not recognized")
    async with _cache_lock:
        _cache[token] = _CacheEntry(info=info, expires_at=_now() + settings.auth_cache_ttl_s)
    return info
