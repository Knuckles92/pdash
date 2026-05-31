"""Weak ETag helpers for optimistic concurrency."""

from __future__ import annotations


def weak_etag(version: int) -> str:
    """Return a weak ETag string from an integer version column."""
    return f'W/"{version}"'


def parse_if_match(value: str | None) -> int | None:
    """Parse an If-Match header value back to its integer version, or None."""
    if not value:
        return None
    v = value.strip()
    if v.startswith("W/"):
        v = v[2:]
    v = v.strip('"')
    try:
        return int(v)
    except ValueError:
        return None
