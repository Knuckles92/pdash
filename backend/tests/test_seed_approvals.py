"""Guards for the canonical example approval inbox (`app.seed_approvals`)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules import validate_config, validate_data
from app.seed_approvals import (
    IDEMPOTENCY_PREFIX,
    SEED_VERSION,
    TITLE_CAPACITY_TREND,
    TITLE_SERVICE_HEALTH,
    home_example_approvals,
)
from app.seed_home import home_example_modules

_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=UTC)
_HOME_PAGE_ID = "pg_test_home"
_PROVISIONAL_ID = "mod_test_provisional"


def _modules_by_title() -> dict[str, str]:
    titles = [spec["title"] for spec in home_example_modules(_NOW)]
    return {title: f"mod_{i}" for i, title in enumerate(titles)}


def test_seed_version_is_one() -> None:
    assert SEED_VERSION == 1


def test_home_example_approvals_include_create_and_updates() -> None:
    modules_by_title = _modules_by_title()
    specs = home_example_approvals(
        _NOW,
        home_page_id=_HOME_PAGE_ID,
        modules_by_title=modules_by_title,
        provisional_id=_PROVISIONAL_ID,
    )
    assert len(specs) == 3
    actions = {s["action_type"] for s in specs}
    assert actions == {"create_module", "update_module_data", "update_module_config"}
    for spec in specs:
        assert spec["idempotency_key"].startswith(IDEMPOTENCY_PREFIX)
        assert spec["decision_reason"]


def test_every_payload_validates_against_module_schemas() -> None:
    modules_by_title = _modules_by_title()
    specs = home_example_approvals(
        _NOW,
        home_page_id=_HOME_PAGE_ID,
        modules_by_title=modules_by_title,
        provisional_id=_PROVISIONAL_ID,
    )
    for spec in specs:
        payload = spec["proposed_payload"]
        action = spec["action_type"]
        if action == "create_module":
            validate_data(payload["type"], payload["data"])
            validate_config(payload["type"], payload["config"])
        elif action == "update_module_data":
            validate_data("key_value", payload["patch"]["data"])
        elif action == "update_module_config":
            validate_config("timeseries", payload["patch"]["config"])


def test_update_specs_skipped_when_target_tiles_missing() -> None:
    specs = home_example_approvals(
        _NOW,
        home_page_id=_HOME_PAGE_ID,
        modules_by_title={},
        provisional_id=_PROVISIONAL_ID,
    )
    assert len(specs) == 1
    assert specs[0]["action_type"] == "create_module"


def test_required_titles_present_in_home_seed() -> None:
    titles = {spec["title"] for spec in home_example_modules(_NOW)}
    assert TITLE_SERVICE_HEALTH in titles
    assert TITLE_CAPACITY_TREND in titles
