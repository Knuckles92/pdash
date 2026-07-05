"""Realtime event bus package (Phase 5).

The single process-wide :class:`EventBus` instance is bound to ``bus`` and is
used by every write path to publish change notifications. Routes
``/api/v1/events`` and ``/api/v1/internal/events`` subscribe to it.
"""

from __future__ import annotations

from .bus import Event, EventBus, validate_internal_topics, validate_topics

bus = EventBus()


__all__ = [
    "Event",
    "EventBus",
    "bus",
    "validate_internal_topics",
    "validate_topics",
]
