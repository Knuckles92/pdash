"""Tests for ``GET /api/v1/activity-log`` and audit-blob spillover."""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)


def test_every_decision_writes_activity_row(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="audit-agent")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    # Propose pending (writes a 'queued' audit row)
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "hi"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="audit-1"),
    )
    assert resp.status_code == 202
    audit_id_pending = resp.headers["X-Audit-Id"]
    request_id = resp.json()["request_id"]

    # Approve (writes a second audit row)
    approve = admin_client.post(
        f"/api/v1/approval-requests/{request_id}/approve", json={}
    )
    assert approve.status_code == 200

    # Activity log should contain both rows referencing the same request_id.
    activity = admin_client.get(
        f"/api/v1/activity-log?target_kind=module&limit=50"
    )
    assert activity.status_code == 200
    items = activity.json()["items"]
    # Filter to our request_id
    matching = [i for i in items if i["request_id"] == request_id]
    assert len(matching) >= 2
    outcomes = sorted({m["outcome"] for m in matching})
    assert "queued" in outcomes
    assert "applied" in outcomes


def test_activity_log_filter_by_actor(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="filter-actor")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "filter test"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="filter-1"),
    )
    resp = admin_client.get(f"/api/v1/activity-log?actor={agent_id}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    assert all(i["actor_id"] == agent_id for i in items)


def test_activity_log_filter_by_outcome(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="filter-outcome")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    # Pending proposal writes a 'queued' row; admin approval writes 'applied'.
    resp = admin_client.post(
        "/api/v1/internal/propose-module",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "outcome test"},
            "config": {},
        },
        headers=internal_headers(agent_id, secret, idempotency_key="outcome-1"),
    )
    request_id = resp.json()["request_id"]
    admin_client.post(f"/api/v1/approval-requests/{request_id}/approve", json={})

    queued = admin_client.get("/api/v1/activity-log?outcome=queued")
    assert queued.status_code == 200
    items = queued.json()["items"]
    assert items
    assert all(i["outcome"] == "queued" for i in items)

    # CSV of outcomes matches either value.
    both = admin_client.get("/api/v1/activity-log?outcome=queued,applied")
    assert both.status_code == 200
    outcomes = {i["outcome"] for i in both.json()["items"]}
    assert outcomes <= {"queued", "applied"}
    assert "queued" in outcomes and "applied" in outcomes


def test_activity_log_get_one(admin_client: TestClient) -> None:
    page_id = home_page_id(admin_client)
    # Use admin create which writes an applied row
    admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "x"},
            "config": {},
        },
    )
    lst = admin_client.get("/api/v1/activity-log?limit=1")
    one_id = lst.json()["items"][0]["id"]
    resp = admin_client.get(f"/api/v1/activity-log/{one_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == one_id


def test_large_payload_spills_to_audit_blobs(admin_client: TestClient) -> None:
    """Force a >32KB payload_summary so write_event spills to audit_blobs."""
    from app.db import get_sessionmaker
    from app.models import ActivityLog, AuditBlob
    from app.services.audit import write_event

    sm = get_sessionmaker()

    async def _go():
        async with sm() as session:
            await session.execute(sql_text("BEGIN IMMEDIATE"))
            # 50KB payload summary
            big = {"chunks": ["x" * 1000 for _ in range(60)]}
            row = await write_event(
                session,
                actor_kind="system",
                actor_id="test-blob",
                action_type="audit_test",
                target_kind=None,
                target_id=None,
                outcome="applied",
                payload_summary=big,
            )
            await session.commit()
            return row.id

    row_id = asyncio.run(_go())
    # The activity_log row's payload_summary should be a stub with _blob_sha256
    resp = admin_client.get(f"/api/v1/activity-log/{row_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "audit_blob" in body
    summary = body["payload_summary"]
    assert summary["_blob_sha256"]
    assert summary["_truncated"] is True
