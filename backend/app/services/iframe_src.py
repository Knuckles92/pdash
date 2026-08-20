"""Iframe src allowlist matching (apply-time + propose-time)."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def host_matches(pattern: str, host: str) -> bool:
    host = host.lower()
    pattern = pattern.lower()
    if pattern.startswith("*."):
        suffix = pattern[1:]  # ".example.com"
        if host == suffix[1:]:
            return True
        return host.endswith(suffix)
    return pattern == host


def is_allowed_iframe_src(
    src: str,
    allowlist: Sequence[tuple[str, str | None]],
) -> bool:
    """``allowlist`` is a sequence of ``(host_pattern, path_prefix)``."""
    try:
        url = urlparse(src)
    except ValueError:
        return False
    if url.scheme not in ("http", "https"):
        return False
    host = (url.hostname or "").lower()
    path = url.path or "/"
    for pattern, path_prefix in allowlist:
        if not host_matches(pattern, host):
            continue
        if path_prefix and not path.startswith(path_prefix):
            continue
        return True
    return False


async def load_allowlist(session: AsyncSession) -> list[tuple[str, str | None]]:
    from ..models import IframeAllowlist

    rows = (await session.execute(select(IframeAllowlist))).scalars().all()
    return [(r.host_pattern, r.path_prefix) for r in rows]


async def assert_iframe_src_allowed(session: AsyncSession, src: str) -> None:
    """Raise ``iframe_host_not_allowed`` if src is not on the admin allowlist."""
    from ..errors import bad_request

    allowlist = await load_allowlist(session)
    if not is_allowed_iframe_src(str(src), allowlist):
        raise bad_request(
            "iframe_host_not_allowed",
            f"iframe host is not allowlisted: {src}",
        )
