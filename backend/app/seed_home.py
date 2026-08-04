"""Canonical default **Home** example modules.

Single source of truth for the dashboard layout that fresh installs are seeded
with (Alembic migration ``0001_initial``) and that ``scripts/reseed_home.py``
rewrites in place during development. This module is **pure data** — it imports
only the stdlib, no SQLAlchemy / Alembic / app models — so it is safe to import
from inside a migration.

Layout & visual intent
-----------------------
The dashboard grid is ``grid-cols-1 lg:grid-cols-2 xl:grid-cols-3`` and each
module carries a ``grid.colspan`` of 1 (1/3), 2 (2/3), or 3 (full). The tiles
are ordered so that at the ``xl`` breakpoint the page reads as:

    ┌───────────────────────────────────────────┐  Welcome (full-width hero)
    ├───────────────────────────┬───────────────┤
    │ Capacity Trend      (2/3) │ Service Health │
    ├───────────────────────────┼───────────────┤
    │ Deployments         (2/3) │ Operations Note│
    ├───────────────────────────┼───────────────┤
    │ Activity Tail       (2/3) │ Quick Links    │
    ├───────────────────────────┼───────────────┤
    │ Embed Preview       (2/3) │ Quick Action   │
    └───────────────────────────┴───────────────┘

Every content row is a wide (2/3) tile beside a narrow (1/3) tile, so the rows
tile cleanly with no gaps. Colours stay inside a cohesive cool / analogous
palette anchored on indigo; every card uses the ``tinted`` treatment except the
``solid`` welcome hero. The result is meant to read as a designed page rather
than a scatter of swatches, while still exercising every module type.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .timefmt import iso_millis

SEED_VERSION = 1


def home_example_modules(now: datetime) -> list[dict]:
    """Return the ordered list of default Home tiles.

    Each entry is a plain dict with ``type``, ``title``, ``colspan``, ``data``
    and ``config`` keys. Callers are responsible for minting ids, attaching the
    page id / ownership / permissions and persisting the rows.
    """
    now_s = iso_millis(now)

    # 12 hourly samples for a smooth area chart.
    cpu = [28, 35, 31, 44, 52, 48, 61, 57, 49, 55, 63, 58]
    mem = [54, 56, 55, 58, 60, 59, 62, 64, 63, 66, 68, 67]
    points = [now - timedelta(hours=(len(cpu) - 1 - i)) for i in range(len(cpu))]

    def _series_points(values: list[int]) -> list[dict]:
        return [{"t": iso_millis(t), "v": v} for t, v in zip(points, values, strict=True)]

    def ago(**kw: int) -> str:
        return iso_millis(now - timedelta(**kw))

    return [
        # 0 ── Welcome hero (full width) ────────────────────────────────────
        {
            "type": "notification",
            "title": "Welcome to pdash",
            "colspan": 3,
            "data": {
                "message": (
                    "This is your private command center. The tiles below are "
                    "sample data so you can see every module type in action — "
                    "edit or clear them from Settings → Pages whenever you're "
                    "ready to make this dashboard your own."
                ),
                "severity": "info",
                "created_at": now_s,
                "icon": "sparkles",
            },
            "config": {
                "dismissible": False,
                "pin_to_top": True,
                "sound": False,
                "appearance": {"theme": "solid", "color": "indigo"},
            },
        },
        # 1 ── Capacity Trend (wide) ────────────────────────────────────────
        {
            "type": "timeseries",
            "title": "Capacity Trend",
            "colspan": 2,
            "data": {
                "series": [
                    {
                        "id": "cpu",
                        "label": "CPU",
                        "color_token": "indigo",
                        "points": _series_points(cpu),
                    },
                    {
                        "id": "memory",
                        "label": "Memory",
                        "color_token": "cyan",
                        "points": _series_points(mem),
                    },
                ],
                "window_start": iso_millis(points[0]),
                "window_end": iso_millis(points[-1]),
            },
            "config": {
                "chart_type": "area",
                "y_axis": {
                    "label": "Utilization",
                    "min": 0,
                    "max": 100,
                    "unit": "%",
                    "format": "percent",
                },
                "show_legend": True,
                "height_px": 260,
                "appearance": {"theme": "tinted", "color": "indigo"},
            },
        },
        # 2 ── Service Health (narrow) ──────────────────────────────────────
        {
            "type": "key_value",
            "title": "Service Health",
            "colspan": 1,
            "data": {
                "fields": [
                    {
                        "key": "Uptime",
                        "value": "27d 14h",
                        "severity": "success",
                        "icon": "circle-check",
                    },
                    {"key": "API latency", "value": 42, "unit": "ms", "severity": "success"},
                    {"key": "Queue depth", "value": 12, "unit": "jobs", "severity": "info"},
                    {"key": "Sync lag", "value": "38s", "severity": "warning"},
                    {"key": "Error rate", "value": 0.2, "unit": "%", "severity": "success"},
                ],
                "updated_at": now_s,
            },
            "config": {
                "layout": "two-column",
                "show_icons": True,
                "value_format": "auto",
                "show_updated_at": True,
                "appearance": {"theme": "tinted", "color": "emerald"},
            },
        },
        # 3 ── Deployments (wide) ───────────────────────────────────────────
        {
            "type": "table",
            "title": "Deployments",
            "colspan": 2,
            "data": {
                "columns": [
                    {"id": "service", "label": "Service", "type": "text"},
                    {"id": "env", "label": "Env", "type": "text"},
                    {"id": "status", "label": "Status", "type": "severity"},
                    {"id": "latency", "label": "p95", "type": "number", "align": "right"},
                    {"id": "deployed", "label": "Deployed", "type": "timestamp"},
                ],
                "rows": [
                    {
                        "row_id": "api",
                        "severity": "success",
                        "cells": {
                            "service": "API",
                            "env": "prod",
                            "status": {"text": "healthy", "severity": "success"},
                            "latency": 42,
                            "deployed": ago(hours=2),
                        },
                    },
                    {
                        "row_id": "web",
                        "severity": "success",
                        "cells": {
                            "service": "Web",
                            "env": "prod",
                            "status": {"text": "healthy", "severity": "success"},
                            "latency": 88,
                            "deployed": ago(hours=5),
                        },
                    },
                    {
                        "row_id": "worker",
                        "severity": "warning",
                        "cells": {
                            "service": "Worker",
                            "env": "prod",
                            "status": {"text": "degraded", "severity": "warning"},
                            "latency": 213,
                            "deployed": ago(hours=1),
                        },
                    },
                    {
                        "row_id": "cache",
                        "severity": "info",
                        "cells": {
                            "service": "Cache",
                            "env": "prod",
                            "status": {"text": "syncing", "severity": "info"},
                            "latency": 7,
                            "deployed": ago(minutes=30),
                        },
                    },
                    {
                        "row_id": "db",
                        "severity": "success",
                        "cells": {
                            "service": "Database",
                            "env": "prod",
                            "status": {"text": "healthy", "severity": "success"},
                            "latency": 12,
                            "deployed": ago(hours=26),
                        },
                    },
                ],
                "updated_at": now_s,
            },
            "config": {
                "row_density": "compact",
                "mobile_layout": "card-stack",
                "default_sort": {"column": "latency", "direction": "desc"},
                "appearance": {"theme": "tinted", "color": "sky"},
            },
        },
        # 4 ── Operations Note (narrow) ─────────────────────────────────────
        {
            "type": "markdown",
            "title": "Operations Note",
            "colspan": 1,
            "data": {
                "body": (
                    "### Daily checklist\n\n"
                    "- Review overnight alerts\n"
                    "- Confirm backups completed\n"
                    "- Check the deployment queue\n"
                    "- Skim the activity feed\n\n"
                    "---\n\n"
                    "Markdown tiles are great for runbooks, handoff notes, and "
                    "release status. They render **headings**, lists, `code`, "
                    "and [links](https://example.com)."
                ),
                "rendered_at": now_s,
            },
            "config": {
                "collapsed_by_default": False,
                "max_height_px": 420,
                "show_rendered_at": True,
                "appearance": {"theme": "tinted", "color": "blue"},
            },
        },
        # 5 ── Activity Tail (wide) ─────────────────────────────────────────
        {
            "type": "log_stream",
            "title": "Activity Tail",
            "colspan": 2,
            "data": {
                "entries": [
                    {
                        "t": ago(minutes=1),
                        "message": "deploy: cache rolled out to prod",
                        "severity": "success",
                        "source": "deploy",
                    },
                    {
                        "t": ago(minutes=4),
                        "message": "worker queue depth 213 (warning threshold 200)",
                        "severity": "warning",
                        "source": "worker",
                    },
                    {
                        "t": ago(minutes=9),
                        "message": "backup manifest uploaded (1.2 GB)",
                        "severity": "success",
                        "source": "backup",
                    },
                    {
                        "t": ago(minutes=15),
                        "message": "scheduler heartbeat received",
                        "severity": "info",
                        "source": "scheduler",
                    },
                    {
                        "t": ago(minutes=22),
                        "message": "agent 'home-bot' proposed a module update",
                        "severity": "info",
                        "source": "approvals",
                    },
                    {
                        "t": ago(minutes=31),
                        "message": "nightly vacuum completed",
                        "severity": "success",
                        "source": "db",
                    },
                ],
                "last_appended_at": ago(minutes=1),
            },
            "config": {
                "ring_buffer_size": 100,
                "order": "newest-first",
                "show_source": True,
                "monospace": True,
                "appearance": {"theme": "tinted", "color": "slate"},
            },
        },
        # 6 ── Quick Links (narrow) ─────────────────────────────────────────
        {
            "type": "link_list",
            "title": "Quick Links",
            "colspan": 1,
            "data": {
                "links": [
                    {
                        "label": "Runbook",
                        "href": "https://example.com/runbook",
                        "description": "Incident response checklist",
                        "severity": "info",
                        "external": True,
                    },
                    {
                        "label": "Grafana",
                        "href": "https://example.com/grafana",
                        "description": "Metrics & dashboards",
                        "severity": "success",
                        "external": True,
                    },
                    {
                        "label": "On-call",
                        "href": "https://example.com/on-call",
                        "description": "This week's schedule",
                        "severity": "warning",
                        "external": True,
                    },
                    {
                        "label": "Repository",
                        "href": "https://example.com/repo",
                        "description": "Source & issues",
                        "severity": "muted",
                        "external": True,
                    },
                ],
                "updated_at": now_s,
            },
            "config": {
                "layout": "list",
                "show_descriptions": True,
                "show_icons": True,
                "open_in_new_tab": True,
                "appearance": {"theme": "tinted", "color": "cyan"},
            },
        },
        # 7 ── Embed Preview (wide) ─────────────────────────────────────────
        {
            "type": "iframe",
            "title": "Embed Preview",
            "colspan": 2,
            "data": {
                "src": "https://example.com/embed",
                "title": "Sample embed",
            },
            "config": {
                "height_px": 240,
                "mobile_height_px": 220,
                "sandbox": [],
                "referrer_policy": "strict-origin-when-cross-origin",
                "show_chrome": True,
                "appearance": {"theme": "tinted", "color": "teal"},
            },
        },
        # 8 ── Quick Action (narrow) ────────────────────────────────────────
        {
            "type": "action_button",
            "title": "Quick Action",
            "colspan": 1,
            "data": {
                "label": "Run health check",
                "action_target_id": "",
                "icon": "activity",
                "severity": "info",
                "disabled": True,
                "last_result": {
                    "fired_at": ago(hours=3),
                    "ok": True,
                    "message": "Last run completed in 1.4s",
                },
            },
            "config": {
                "confirm": True,
                "confirm_text": "Connect an action target before running.",
                "cooldown_seconds": 0,
                "style": "secondary",
                "show_last_result": True,
                "appearance": {"theme": "tinted", "color": "violet"},
            },
        },
        # 9 ── Storage & Backups (full-width progress band) ───────────────
        {
            "type": "progress",
            "title": "Storage & Backups",
            "colspan": 3,
            "data": {
                "bars": [
                    {
                        "id": "disk",
                        "label": "Disk usage",
                        "current": 1.8,
                        "target": 2,
                        "unit": "TB",
                        "severity": "warning",
                        "hint": "Primary volume /data",
                    },
                    {
                        "id": "backups",
                        "label": "Backups completed",
                        "current": 14,
                        "target": 14,
                        "unit": "jobs",
                        "severity": "success",
                    },
                    {
                        "id": "snapshots",
                        "label": "Snapshots retained",
                        "current": 38,
                        "target": 50,
                        "unit": "daily",
                        "severity": "info",
                    },
                    {
                        "id": "mailbox",
                        "label": "Mailbox",
                        "current": 3.2,
                        "target": 10,
                        "unit": "GB",
                        "severity": "success",
                    },
                ],
                "updated_at": now_s,
            },
            "config": {
                "show_values": True,
                "show_percent": True,
                "density": "normal",
                "sort": "as-is",
                "appearance": {"theme": "tinted", "color": "blue"},
            },
        },
    ]
