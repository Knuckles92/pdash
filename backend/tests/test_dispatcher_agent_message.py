"""Tests for the agent_message action_target dispatcher."""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    internal_headers,
    register_agent,
)


def _count_messages_for(agent_id: str) -> tuple[int, dict | None]:
    """Return (count, last_payload) of agent_messages rows for `agent_id`."""
    from sqlalchemy import select

    from app.db import get_sessionmaker
    from app.models import AgentMessage

    sm = get_sessionmaker()

    async def _go() -> tuple[int, dict | None]:
        async with sm() as session:
            rows = (
                await session.execute(
                    select(AgentMessage).where(AgentMessage.to_agent_id == agent_id)
                )
            ).scalars().all()
            last = json.loads(rows[-1].payload) if rows else None
            return len(rows), last

    return asyncio.run(_go())


def test_agent_message_dispatch_inserts_row(admin_client: TestClient) -> None:
    # Source agent who fires the action.
    source_id, _ = register_agent(admin_client, name="agt-msg-source")
    # Destination agent who receives the message.
    dest_id, _ = register_agent(admin_client, name="agt-msg-dest")
    secret = get_service_secret()

    target = admin_client.post(
        "/api/v1/action-targets",
        json={
            "name": "nudge-dest",
            "kind": "agent_message",
            "config": {"to_agent_id": dest_id},
            "mode": "sync",
        },
    )
    assert target.status_code == 201, target.text
    tid = target.json()["id"]

    resp = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid, "payload": {"hello": "from source"}},
        headers=internal_headers(source_id, secret, idempotency_key="am-ok"),
    )
    assert resp.status_code == 202
    req_id = resp.json()["request_id"]

    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={}
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["applied"] is True

    detail = admin_client.get(f"/api/v1/approval-requests/{req_id}").json()
    assert detail["status"] == "applied"
    er = detail["execution_result"]
    assert er["ok"] is True
    assert er["to_agent_id"] == dest_id
    assert er["message_id"].startswith("msg_")

    count, last_payload = _count_messages_for(dest_id)
    assert count == 1
    assert last_payload == {"hello": "from source"}


def test_agent_message_dispatch_missing_to_agent_id_fails(
    admin_client: TestClient,
) -> None:
    src_id, _ = register_agent(admin_client, name="am-bad-src")
    secret = get_service_secret()
    target = admin_client.post(
        "/api/v1/action-targets",
        json={
            "name": "no-recipient",
            "kind": "agent_message",
            "config": {},  # missing to_agent_id
            "mode": "sync",
        },
    )
    tid = target.json()["id"]
    resp = admin_client.post(
        "/api/v1/internal/fire-action",
        json={"target_id": tid, "payload": {}},
        headers=internal_headers(src_id, secret, idempotency_key="am-bad"),
    )
    req_id = resp.json()["request_id"]
    approve = admin_client.post(
        f"/api/v1/approval-requests/{req_id}/approve", json={}
    )
    assert approve.status_code == 200
    detail = admin_client.get(f"/api/v1/approval-requests/{req_id}").json()
    er = detail["execution_result"]
    assert er["ok"] is False
    assert "to_agent_id" in (er.get("error") or "")
