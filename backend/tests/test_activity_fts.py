"""Tests for FTS5-backed activity_log search.

Phase 6: ``GET /api/v1/activity-log?q=...`` joins the FTS5 virtual table
``activity_log_fts`` instead of using SQL LIKE, with ``bm25`` ordering.

The activity_log_fts table indexes ``payload_summary``, ``outcome``, and
``action_type``. To exercise FTS we seed rows by directly writing audit
events with controllable strings in the payload summary (the orchestrator
truncates real payloads to just ``payload_keys``).
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient


def _write_audit(
    actor_id: str,
    action_type: str,
    *,
    payload: dict,
    outcome: str = "applied",
) -> int:
    """Insert one activity_log row via the audit service. Returns its id."""
    from sqlalchemy import text as sql_text

    from app.db import get_sessionmaker
    from app.services.audit import write_event

    sm = get_sessionmaker()

    async def _go() -> int:
        async with sm() as session:
            await session.execute(sql_text("BEGIN IMMEDIATE"))
            row = await write_event(
                session,
                actor_kind="system",
                actor_id=actor_id,
                action_type=action_type,
                target_kind=None,
                target_id=None,
                outcome=outcome,
                payload_summary=payload,
            )
            await session.commit()
            return row.id

    return asyncio.run(_go())


def test_fts_search_matches_payload_summary(admin_client: TestClient) -> None:
    _write_audit("fts-1", "create_module", payload={"note": "needle alpha"})
    _write_audit("fts-2", "create_module", payload={"note": "elephant beta"})
    _write_audit("fts-3", "create_module", payload={"note": "needle gamma"})

    resp = admin_client.get("/api/v1/activity-log?q=needle")
    assert resp.status_code == 200
    items = resp.json()["items"]
    notes = [(i.get("payload_summary") or {}).get("note") for i in items]
    assert "needle alpha" in notes
    assert "needle gamma" in notes
    assert "elephant beta" not in notes


def test_fts_search_action_type_token(admin_client: TestClient) -> None:
    """action_type is indexed; we can search for it directly."""
    _write_audit("fts-act", "fire_action_button", payload={"x": 1})
    _write_audit("fts-act", "create_module", payload={"x": 2})
    resp = admin_client.get("/api/v1/activity-log?q=fire_action_button")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    assert all(i["action_type"] == "fire_action_button" for i in items)


def test_fts_search_empty_q_falls_back_to_plain_listing(
    admin_client: TestClient,
) -> None:
    _write_audit("plain-1", "create_module", payload={"x": 1})
    resp = admin_client.get("/api/v1/activity-log?q=")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1


def test_fts_search_combined_with_actor_filter(admin_client: TestClient) -> None:
    _write_audit("alice-fts", "create_module", payload={"note": "fancyterm"})
    _write_audit("bob-fts", "create_module", payload={"note": "fancyterm"})
    resp = admin_client.get(
        "/api/v1/activity-log?q=fancyterm&actor=alice-fts"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    assert all(i["actor_id"] == "alice-fts" for i in items)


def test_fts_search_no_hits(admin_client: TestClient) -> None:
    _write_audit("none-1", "create_module", payload={"note": "ordinary"})
    resp = admin_client.get("/api/v1/activity-log?q=zzzzzzz_no_such_token")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items == []


def test_fts_search_special_chars_are_neutralized(
    admin_client: TestClient,
) -> None:
    """Punctuation in q must not break the query (FTS5 syntax is fragile)."""
    _write_audit("punct-1", "create_module", payload={"note": "punct"})
    # FTS5 punctuation like double-quotes / parens would normally error out
    # without our sanitizer.
    resp = admin_client.get('/api/v1/activity-log?q="(*&^%$#@!')
    assert resp.status_code == 200


def test_fts_prefix_match(admin_client: TestClient) -> None:
    """Prefix matching via FTS5 ``*`` suffix lets us find via short prefixes."""
    _write_audit(
        "prefix-1", "create_module", payload={"note": "uniqprefixfoobar"}
    )
    resp = admin_client.get("/api/v1/activity-log?q=uniqprefix")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(
        (i.get("payload_summary") or {}).get("note") == "uniqprefixfoobar"
        for i in items
    )


def test_fts_index_kept_in_sync_on_insert(admin_client: TestClient) -> None:
    """The AFTER INSERT trigger should make new rows immediately searchable."""
    token = "very_specific_token_xyz_42"
    rid = _write_audit("trigger-test", "create_module", payload={"note": token})
    assert rid > 0
    resp = admin_client.get(f"/api/v1/activity-log?q={token}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    assert items[0]["id"] == rid
