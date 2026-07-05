"""Helpers for queueing events to publish after the current DB transaction commits.

Publishing immediately would race with the writer — readers subscribed to the
SSE feed might see the event before the underlying row is visible to other
sessions. Instead we attach a one-shot ``after_commit`` listener on the
SQLAlchemy session that fires the publish.

If the session rolls back the queued events are discarded.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession

from .bus import Event

logger = logging.getLogger(__name__)


# Stash queued publishes on the AsyncSession itself. The mapping survives the
# duration of the transaction; the after-commit handler drains it.
_QUEUE_ATTR = "_pdash_pending_publishes"


def publish_after_commit(
    session: AsyncSession, topic: str, kind: str, payload: dict[str, Any]
) -> None:
    """Queue an event for publish after the session's next commit.

    The event is dropped on rollback. Calls outside a transaction (rare,
    e.g. read sessions) fall back to immediate publish since there's no
    transactional boundary to wait on.
    """
    sync_session = session.sync_session
    queue: list[tuple[str, str, dict[str, Any]]] = getattr(
        sync_session, _QUEUE_ATTR, []
    )
    if not hasattr(sync_session, _QUEUE_ATTR):
        setattr(sync_session, _QUEUE_ATTR, queue)

        @sa_event.listens_for(sync_session, "after_commit")
        def _drain(_session) -> None:  # noqa: ANN001
            from . import bus  # local import to avoid module-level cycles
            pending: list[tuple[str, str, dict[str, Any]]] = getattr(
                sync_session, _QUEUE_ATTR, []
            )
            for t, k, p in pending:
                try:
                    bus.publish(t, k, p)
                except Exception:  # noqa: BLE001
                    logger.exception("EventBus publish failed for %s/%s", t, k)
            # Clear after delivery.
            setattr(sync_session, _QUEUE_ATTR, [])

        @sa_event.listens_for(sync_session, "after_rollback")
        def _discard(_session) -> None:  # noqa: ANN001
            setattr(sync_session, _QUEUE_ATTR, [])

    queue.append((topic, kind, payload))


def publish_now(topic: str, kind: str, payload: dict[str, Any]) -> Event:
    """Publish immediately, ignoring transaction boundaries.

    Use this only when there is no surrounding transaction (e.g. inside a
    background task that already committed its own write).
    """
    from . import bus
    return bus.publish(topic, kind, payload)


__all__ = ["publish_after_commit", "publish_now"]
