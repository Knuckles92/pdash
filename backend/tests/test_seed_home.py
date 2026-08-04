"""Guards for the canonical default Home layout (`app.seed_home`).

Keeps the seed honest: every tile validates against its real module schema,
the layout covers every seedable module type (all except `file`, which needs a
registered file at runtime), and the colspans tile the 3-column `xl` grid.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules import MODULE_TYPES, validate_config, validate_data
from app.seed_home import SEED_VERSION, home_example_modules

_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=UTC)


def test_seed_version_is_one() -> None:
    # The DB-level test (test_modules) asserts seeded rows carry seed_version 1.
    assert SEED_VERSION == 1


def test_every_tile_validates_against_its_schema() -> None:
    for spec in home_example_modules(_NOW):
        # Raises pydantic ValidationError if the data/config drifts from schema.
        validate_data(spec["type"], spec["data"])
        validate_config(spec["type"], spec["config"])


def test_layout_covers_every_module_type_once() -> None:
    types = [spec["type"] for spec in home_example_modules(_NOW)]
    # Excluded from the home seed:
    # - `file` references a registered file that only exists once an agent/admin
    #   actually drops + registers one.
    # - `sticky_note` only belongs on a corkboard page, not the default grid.
    # - `html` is the canvas-page surface; agents propose it deliberately, and
    #   a demo document would be dead weight on the default grid.
    excluded = {"file", "sticky_note", "html"}
    expected = sorted(t for t in MODULE_TYPES if t not in excluded)
    assert sorted(types) == expected
    assert len(types) == len(set(types)), "each module type should appear exactly once"


def test_colspans_tile_the_three_column_grid_without_gaps() -> None:
    """Simulate CSS grid sparse auto-placement across 3 columns."""
    columns = 3
    cursor = 0
    gaps = 0
    for spec in home_example_modules(_NOW):
        span = min(int(spec.get("colspan", 1)), columns)
        remaining = columns - cursor
        if span > remaining:
            gaps += remaining  # this row can't fit the tile; the tail is a gap
            cursor = 0
        cursor += span
        if cursor >= columns:
            cursor = 0
    assert gaps == 0, "default layout leaves empty cells in the xl 3-column grid"
