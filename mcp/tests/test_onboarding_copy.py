"""Unit tests for hosted skill + onboarding copy (no live backend)."""

from __future__ import annotations

from app.onboarding import onboarding_payload, skill_markdown


def test_onboarding_payload_describes_current_defaults() -> None:
    notes = " ".join(onboarding_payload()["notes"])
    assert "ordinary widgets typically auto-apply" in notes
    assert "list_my_pending_requests about every 5s" in notes
    assert "get_module_schema is optional" in notes
    assert "update_module merges" in notes


def test_skill_markdown_covers_auto_apply_and_pending() -> None:
    body = skill_markdown("http://example.test/mcp")
    assert "name: pdash-onboarding" in body
    assert "list_my_pending_requests` about every 5 seconds" in body
    assert "What typically auto-applies" in body
    assert "First `html`, `iframe`, or `action_button`" in body
    assert "grid.colspan` is 1, 2, or 3" in body
    assert "allow-scripts` without `allow-same-origin" in body
    assert '"url": "http://example.test/mcp"' in body
