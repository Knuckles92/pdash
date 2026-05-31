"""Stdlib-only timestamp formatting, shared across the app.

Kept dependency-free (no SQLAlchemy / Alembic / app models) so the seed modules
that import it stay safe to import from inside a migration. ``app.models``
re-exports :func:`utcnow_iso` for backwards compatibility.
"""

from __future__ import annotations

from datetime import UTC, datetime


def iso_millis(dt: datetime) -> str:
    """Millisecond-precision ISO-8601 ``Z`` timestamp for a datetime."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def utcnow_iso() -> str:
    """Current UTC time as a millisecond ISO-8601 ``Z`` timestamp."""
    return iso_millis(datetime.now(UTC))
