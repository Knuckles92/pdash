"""Tests for the approval lifecycle state machine + expiry sweeper."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text as sql_text

from app.approval import lifecycle
from app.approval.expiry import expire_stale_pending
from app.db import get_sessionmaker
from app.ids import new_id
from app.models import Agent, ApprovalRequest, utcnow_iso


async def _make_agent(session, name: str = "test-agent") -> str:
    aid = new_id("agt")
    row = Agent(
        id=aid,
        display_name=name,
        api_key_hash="dummy",
        permissions="{}",
        status="active",
        created_at=utcnow_iso(),
    )
    session.add(row)
    await session.flush()
    return aid


async def _make_request(session, *, agent_id: str, action_type: str = "create_module") -> ApprovalRequest:
    apr = ApprovalRequest(
        id=new_id("apr"),
        agent_id=agent_id,
        action_type=action_type,
        target_kind="module",
        target_id=None,
        proposed_payload="{}",
        status="pending",
        created_at=utcnow_iso(),
    )
    session.add(apr)
    await session.flush()
    return apr


def test_invalid_transition_raises():
    """Approving an already-applied request must raise InvalidTransition."""
    apr = ApprovalRequest(
        id=new_id("apr"),
        agent_id="agt_x",
        action_type="create_module",
        proposed_payload="{}",
        status="applied",
        created_at=utcnow_iso(),
    )
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.mark_approved(apr, decided_by="admin")
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.mark_denied(apr, decided_by="admin")
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.mark_expired(apr)


def test_pending_to_approved_to_applied():
    apr = ApprovalRequest(
        id=new_id("apr"),
        agent_id="agt_x",
        action_type="create_module",
        proposed_payload="{}",
        status="pending",
        created_at=utcnow_iso(),
    )
    lifecycle.mark_approved(apr, decided_by="admin:test", decision_reason="ok")
    assert apr.status == "approved"
    assert apr.decided_by == "admin:test"
    assert apr.decision_reason == "ok"

    lifecycle.mark_applied(apr)
    assert apr.status == "applied"
    assert apr.applied_at is not None


def test_pending_to_denied():
    apr = ApprovalRequest(
        id=new_id("apr"),
        agent_id="agt_x",
        action_type="create_module",
        proposed_payload="{}",
        status="pending",
        created_at=utcnow_iso(),
    )
    lifecycle.mark_denied(apr, decided_by="admin:test", decision_reason="no")
    assert apr.status == "denied"
    assert apr.decision_reason == "no"


def test_executed_requires_applied_state():
    apr = ApprovalRequest(
        id=new_id("apr"),
        agent_id="agt_x",
        action_type="fire_action_button",
        proposed_payload="{}",
        status="pending",
        created_at=utcnow_iso(),
    )
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.mark_executed(apr, result={"ok": True})

    lifecycle.mark_approved(apr, decided_by="admin:test")
    lifecycle.mark_applied(apr)
    lifecycle.mark_executed(apr, result={"ok": True, "status_code": 200})
    assert apr.executed_at is not None
    assert json.loads(apr.execution_result)["ok"] is True


def test_expire_stale_pending_flips_rows(initialized_db):
    """Pending rows past expires_at should flip to ``expired`` via the sweeper."""
    sm = get_sessionmaker()

    async def _go():
        async with sm() as session:
            await session.execute(sql_text("BEGIN IMMEDIATE"))
            agent_id = await _make_agent(session, name="expiry-test")

            # Stale row (expired 5 minutes ago)
            stale = ApprovalRequest(
                id=new_id("apr"),
                agent_id=agent_id,
                action_type="create_module",
                proposed_payload="{}",
                status="pending",
                created_at=utcnow_iso(),
                expires_at=(datetime.now(UTC) - timedelta(minutes=5))
                .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            )
            # Fresh row (expires in the future)
            fresh = ApprovalRequest(
                id=new_id("apr"),
                agent_id=agent_id,
                action_type="create_module",
                proposed_payload="{}",
                status="pending",
                created_at=utcnow_iso(),
                expires_at=(datetime.now(UTC) + timedelta(days=1))
                .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            )
            session.add_all([stale, fresh])
            await session.flush()
            stale_id, fresh_id = stale.id, fresh.id

            count = await expire_stale_pending(session)
            await session.commit()
            return count, stale_id, fresh_id

        async with sm() as session:
            stale_row = await session.get(ApprovalRequest, stale_id)
            fresh_row = await session.get(ApprovalRequest, fresh_id)
            assert stale_row.status == "expired"
            assert fresh_row.status == "pending"

    count, stale_id, fresh_id = asyncio.run(_go())
    assert count == 1

    async def _verify():
        async with sm() as session:
            stale_row = await session.get(ApprovalRequest, stale_id)
            fresh_row = await session.get(ApprovalRequest, fresh_id)
            assert stale_row.status == "expired"
            assert fresh_row.status == "pending"

    asyncio.run(_verify())
