"""Approval engine matching tests."""

from __future__ import annotations

import asyncio

import pytest

from app.approval.engine import (
    CachedRule,
    DecisionRequest,
    _rule_matches,
    bump_rules_version,
    decide,
    get_rule_cache,
    reset_cache_for_tests,
)
from app.db import get_sessionmaker
from app.ids import new_id
from app.models import ApprovalRule, utcnow_iso


@pytest.fixture
def reset_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def _cached(
    *,
    agent_id: str = "*",
    action_type: str = "create_module",
    module_type: str | None = None,
    module_id: str | None = None,
    page_id: str | None = None,
    owner_scope: str = "any",
    outcome: str = "auto_approve",
    priority: int = 100,
    rule_id: str = "rule_x",
    created_at: str = "2026-05-01T00:00:00.000Z",
) -> CachedRule:
    return CachedRule(
        id=rule_id,
        agent_id=agent_id,
        action_type=action_type,
        module_type=module_type,
        module_id=module_id,
        page_id=page_id,
        owner_scope=owner_scope,
        outcome=outcome,  # type: ignore[arg-type]
        priority=priority,
        is_builtin=False,
        created_at=created_at,
    )


def _req(
    *,
    action_type: str = "create_module",
    agent_id: str = "agt_test",
    module_type: str | None = None,
    module_id: str | None = None,
    page_id: str | None = None,
    agent_owns_target: bool = False,
) -> DecisionRequest:
    return DecisionRequest(
        action_type=action_type,
        agent_id=agent_id,
        module_type=module_type,
        module_id=module_id,
        page_id=page_id,
        agent_owns_target=agent_owns_target,
    )


def test_wildcard_rule_matches_any_agent():
    rule = _cached(agent_id="*")
    assert _rule_matches(rule, _req(agent_id="agt_anyone"))


def test_concrete_agent_rule_must_match_id():
    rule = _cached(agent_id="agt_alpha")
    assert _rule_matches(rule, _req(agent_id="agt_alpha"))
    assert not _rule_matches(rule, _req(agent_id="agt_beta"))


def test_module_type_filter():
    rule = _cached(module_type="markdown")
    assert _rule_matches(rule, _req(module_type="markdown"))
    assert not _rule_matches(rule, _req(module_type="key_value"))


def test_module_type_star_matches_any():
    rule = _cached(module_type="*")
    assert _rule_matches(rule, _req(module_type="markdown"))
    assert _rule_matches(rule, _req(module_type="iframe"))


def test_owner_scope_self():
    rule = _cached(owner_scope="self")
    assert _rule_matches(rule, _req(agent_owns_target=True))
    assert not _rule_matches(rule, _req(agent_owns_target=False))


def test_owner_scope_other():
    rule = _cached(owner_scope="other")
    assert _rule_matches(rule, _req(agent_owns_target=False))
    assert not _rule_matches(rule, _req(agent_owns_target=True))


def test_specificity_score_counts_dimensions():
    bare = _cached()  # all wildcards, owner_scope=any
    assert bare.specificity == 0
    with_agent = _cached(agent_id="agt_x")
    assert with_agent.specificity == 1
    with_mod_type = _cached(module_type="markdown")
    assert with_mod_type.specificity == 1
    full = _cached(
        agent_id="agt_x",
        module_type="markdown",
        module_id="mod_y",
        page_id="pg_z",
        owner_scope="self",
    )
    assert full.specificity == 5


@pytest.mark.asyncio
async def test_decide_default_no_rule_returns_prompt(initialized_db, reset_cache):
    sm = get_sessionmaker()
    async with sm() as session:
        # First, disable all built-in rules so we hit the no-match path.
        from sqlalchemy import update
        await session.execute(
            update(ApprovalRule).where(ApprovalRule.action_type == "create_page").values(enabled=0)
        )
        await session.commit()
    bump_rules_version()
    async with sm() as session:
        decision = await decide(
            session,
            _req(action_type="create_page", agent_id="agt_test"),
        )
        assert decision.status == "prompt"
        assert decision.rule_id is None


@pytest.mark.asyncio
async def test_decide_builtin_self_update_auto_approves(initialized_db, reset_cache):
    sm = get_sessionmaker()
    async with sm() as session:
        decision = await decide(
            session,
            _req(
                action_type="update_module_data",
                agent_id="agt_alpha",
                module_type="markdown",
                module_id="mod_self_owned",
                agent_owns_target=True,
            ),
        )
        assert decision.status == "auto_approve"
        assert decision.rule_id is not None


@pytest.mark.asyncio
async def test_decide_more_specific_rule_wins(initialized_db, reset_cache):
    """A custom narrow auto_approve overrides the broad built-in prompt."""
    sm = get_sessionmaker()
    async with sm() as session:
        from sqlalchemy import text as sql_text
        await session.execute(sql_text("BEGIN IMMEDIATE"))
        # Add a narrow rule that auto-approves create_module for a specific agent.
        custom = ApprovalRule(
            id=new_id("rule"),
            agent_id="agt_special",
            action_type="create_module",
            module_type=None,
            module_id=None,
            page_id=None,
            owner_scope="any",
            outcome="auto_approve",
            priority=50,
            is_builtin=0,
            enabled=1,
            notes="test",
            created_at=utcnow_iso(),
            created_by="test",
            application_count=0,
        )
        session.add(custom)
        await session.commit()
    bump_rules_version()
    async with sm() as session:
        decision = await decide(
            session,
            _req(action_type="create_module", agent_id="agt_special"),
        )
        assert decision.status == "auto_approve"


@pytest.mark.asyncio
async def test_rule_cache_invalidation_via_version(initialized_db, reset_cache):
    sm = get_sessionmaker()
    async with sm() as session:
        cache_v1 = await get_rule_cache(session)
        first_count = sum(len(b) for b in cache_v1.rules_by_action.values())
    bump_rules_version()
    async with sm() as session:
        cache_v2 = await get_rule_cache(session)
        assert cache_v2 is not cache_v1
        assert sum(len(b) for b in cache_v2.rules_by_action.values()) == first_count
