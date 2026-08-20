"""Coercion, extra=ignore, and merge-on-update."""

from __future__ import annotations

from app.modules import merge_and_validate_data, validate_config, validate_data
from app.modules._common import Appearance, Icon
from pydantic import TypeAdapter, ValidationError
import pytest


def test_extra_keys_ignored_on_markdown() -> None:
    out = validate_data("markdown", {"body": "hi", "comment": "nope"})
    assert out["body"] == "hi"
    assert "comment" not in out


def test_merge_omitted_fields_keep_existing() -> None:
    existing = {"body": "old", "rendered_at": None}
    merged = merge_and_validate_data("markdown", existing, {"body": "new"})
    assert merged["body"] == "new"


def test_table_row_patch_keeps_columns() -> None:
    existing = {
        "columns": [{"id": "n", "label": "Name", "type": "text"}],
        "rows": [{"cells": {"n": "a"}}],
    }
    merged = merge_and_validate_data(
        "table", existing, {"rows": [{"cells": {"n": "b"}}]}
    )
    assert merged["columns"][0]["id"] == "n"
    assert merged["rows"][0]["cells"]["n"] == "b"


def test_schemeless_iframe_src_gets_https() -> None:
    out = validate_data("iframe", {"src": "grafana.local/d/x"})
    assert str(out["src"]).startswith("https://grafana.local")


def test_javascript_url_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_data("iframe", {"src": "javascript:alert(1)"})


def test_mailto_link_ok() -> None:
    out = validate_data(
        "link_list", {"links": [{"label": "me", "href": "mailto:a@b.co"}]}
    )
    assert "mailto:" in str(out["links"][0]["href"])


def test_icon_pascal_and_snake_normalize() -> None:
    adapter = TypeAdapter(Icon)
    assert adapter.validate_python("CheckCircle") == "check-circle"
    assert adapter.validate_python("check_circle") == "check-circle"
    assert adapter.validate_python("check-circle") == "check-circle"


def test_appearance_accepts_hex() -> None:
    a = Appearance.model_validate({"theme": "tinted", "color": "#10b981"})
    assert a.color == "#10b981"
    named = Appearance.model_validate({"color": "emerald"})
    assert named.color == "emerald"


def test_appearance_rejects_garbage_color() -> None:
    with pytest.raises(ValidationError):
        Appearance.model_validate({"color": "not-a-color"})


def test_hex_in_config_round_trips() -> None:
    out = validate_config("markdown", {"appearance": {"color": "#3b82f6"}})
    assert out["appearance"]["color"] == "#3b82f6"
