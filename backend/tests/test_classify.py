"""Unit tests for the update risk classifier."""

from __future__ import annotations

from app.approval.classify import classify_update


def test_table_rows_are_data_not_capability() -> None:
    existing = {
        "columns": [{"id": "n", "label": "Name", "type": "text"}],
        "rows": [{"cells": {"n": "a"}}],
    }
    patch = {"data": {"rows": [{"cells": {"n": "b"}}]}}
    assert classify_update("table", existing, {}, patch) == "update_module_data"


def test_table_column_change_is_capability() -> None:
    existing = {
        "columns": [{"id": "n", "label": "Name", "type": "text"}],
        "rows": [],
    }
    patch = {
        "data": {
            "columns": [{"id": "n", "label": "Name", "type": "number"}],
            "rows": [],
        }
    }
    assert classify_update("table", existing, {}, patch) == "update_module_capability"


def test_iframe_src_change_is_capability() -> None:
    existing = {"src": "https://a.example/x"}
    patch = {"data": {"src": "https://b.example/x"}}
    assert classify_update("iframe", existing, {}, patch) == "update_module_capability"


def test_iframe_sandbox_loosen_is_capability() -> None:
    patch = {"config": {"sandbox": ["allow-scripts", "allow-same-origin"]}}
    assert (
        classify_update("iframe", {"src": "https://a.example"}, {}, patch)
        == "update_module_capability"
    )


def test_iframe_height_is_config() -> None:
    patch = {"config": {"height_px": 800}}
    assert (
        classify_update("iframe", {"src": "https://a.example"}, {"height_px": 480}, patch)
        == "update_module_config"
    )


def test_action_retarget_is_capability() -> None:
    existing = {"label": "Go", "action_target_id": "act_1"}
    patch = {"data": {"action_target_id": "act_2"}}
    assert (
        classify_update("action_button", existing, {"confirm": True}, patch)
        == "update_module_capability"
    )


def test_confirm_true_to_false_is_capability() -> None:
    patch = {"config": {"confirm": False}}
    assert (
        classify_update(
            "action_button",
            {"label": "Go", "action_target_id": "act_1"},
            {"confirm": True},
            patch,
        )
        == "update_module_capability"
    )


def test_confirm_false_to_true_is_config() -> None:
    patch = {"config": {"confirm": True}}
    assert (
        classify_update(
            "action_button",
            {"label": "Go", "action_target_id": "act_1"},
            {"confirm": False},
            patch,
        )
        == "update_module_config"
    )


def test_mixed_data_and_src_is_capability() -> None:
    existing = {"src": "https://a.example", "title": "A"}
    patch = {"data": {"title": "B", "src": "https://b.example"}, "config": {"height_px": 900}}
    assert classify_update("iframe", existing, {}, patch) == "update_module_capability"


def test_title_only_is_meta() -> None:
    assert classify_update("markdown", {"body": "x"}, {}, {"title": "Hi"}) == "update_module_meta"


def test_markdown_body_is_data() -> None:
    assert (
        classify_update("markdown", {"body": "x"}, {}, {"data": {"body": "y"}})
        == "update_module_data"
    )
