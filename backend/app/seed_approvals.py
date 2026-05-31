"""Canonical default **example approval requests** for the admin inbox.

Single source of truth for the demo agent + pending requests that fresh installs
are seeded with (Alembic migration ``0004_seed_example_approvals``) and that
``scripts/reseed_approvals.py`` rewrites in place during development.

This module is mostly **pure data** — stdlib only in the spec builders — so it
is safe to import from inside a migration. Callers hash
:const:`EXAMPLE_AGENT_KEY_PLAINTEXT` at insert time.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .timefmt import iso_millis

SEED_VERSION = 1

EXAMPLE_AGENT_DISPLAY_NAME = "Home Bot"
EXAMPLE_AGENT_DESCRIPTION = (
    "Sample agent for demo approval requests. No MCP API key is issued — "
    "register a real agent under Settings when you connect an AI client."
)
EXAMPLE_AGENT_KEY_PLAINTEXT = "pdash_default_example:home-bot-no-key"
EXAMPLE_AGENT_PERMISSIONS: dict = {
    "pdash_default_example": True,
    "seed_version": SEED_VERSION,
}

IDEMPOTENCY_PREFIX = "pdash_default_example:"

TITLE_SERVICE_HEALTH = "Service Health"
TITLE_CAPACITY_TREND = "Capacity Trend"

EXAMPLE_RATIONALE = (
    "Example request — safe to deny; approving will apply this change."
)

PENDING_TTL_DAYS = 7


def expires_at(now: datetime) -> str:
    """ISO-8601 UTC timestamp when a seeded pending row should expire."""
    return iso_millis(now + timedelta(days=PENDING_TTL_DAYS))


def home_example_approvals(
    now: datetime,
    *,
    home_page_id: str,
    modules_by_title: dict[str, str],
    provisional_id: str,
) -> list[dict]:
    """Return insert-ready approval request specs for the Home demo inbox.

    Each entry is a plain dict with ``action_type``, ``target_kind``,
    ``target_id``, ``proposed_payload``, ``idempotency_key``, and
    ``decision_reason``. Callers mint ``apr_*`` ids, attach ``agent_id``,
    set ``status='pending'``, and persist the rows.

    Update examples are omitted when the referenced example tile was removed
    from the Home page.
    """
    now_s = iso_millis(now)
    specs: list[dict] = []

    create_payload = {
        "type": "markdown",
        "page_id": home_page_id,
        "title": "Incident summary",
        "position": 99,
        "grid": {"colspan": 2},
        "permissions": {},
        "data": {
            "body": (
                "### Open incidents\n\n"
                "- **API**: elevated latency (p95 88ms)\n"
                "- **Worker**: queue backlog above threshold\n\n"
                "_Example proposal — deny or approve to explore the flow._"
            ),
        },
        "config": {
            "collapsed_by_default": False,
            "max_height_px": 400,
            "show_rendered_at": False,
            "appearance": {"theme": "tinted", "color": "amber"},
        },
        "provisional_id": provisional_id,
    }
    specs.append(
        {
            "action_type": "create_module",
            "target_kind": "module",
            "target_id": provisional_id,
            "proposed_payload": create_payload,
            "idempotency_key": f"{IDEMPOTENCY_PREFIX}create-incident",
            "decision_reason": EXAMPLE_RATIONALE,
        }
    )

    service_health_id = modules_by_title.get(TITLE_SERVICE_HEALTH)
    if service_health_id:
        specs.append(
            {
                "action_type": "update_module_data",
                "target_kind": "module",
                "target_id": service_health_id,
                "proposed_payload": {
                    "id": service_health_id,
                    "patch": {
                        "data": {
                            "fields": [
                                {
                                    "key": "Uptime",
                                    "value": "27d 14h",
                                    "severity": "success",
                                    "icon": "circle-check",
                                },
                                {
                                    "key": "API latency",
                                    "value": 42,
                                    "unit": "ms",
                                    "severity": "success",
                                },
                                {
                                    "key": "Queue depth",
                                    "value": 18,
                                    "unit": "jobs",
                                    "severity": "warning",
                                },
                                {
                                    "key": "Sync lag",
                                    "value": "52s",
                                    "severity": "warning",
                                },
                                {
                                    "key": "Error rate",
                                    "value": 0.2,
                                    "unit": "%",
                                    "severity": "success",
                                },
                            ],
                            "updated_at": now_s,
                        },
                    },
                },
                "idempotency_key": f"{IDEMPOTENCY_PREFIX}update-service-health",
                "decision_reason": EXAMPLE_RATIONALE,
            }
        )

    capacity_trend_id = modules_by_title.get(TITLE_CAPACITY_TREND)
    if capacity_trend_id:
        specs.append(
            {
                "action_type": "update_module_config",
                "target_kind": "module",
                "target_id": capacity_trend_id,
                "proposed_payload": {
                    "id": capacity_trend_id,
                    "patch": {
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
                            "height_px": 320,
                            "appearance": {"theme": "tinted", "color": "indigo"},
                        },
                    },
                },
                "idempotency_key": f"{IDEMPOTENCY_PREFIX}update-capacity-trend",
                "decision_reason": EXAMPLE_RATIONALE,
            }
        )

    return specs
