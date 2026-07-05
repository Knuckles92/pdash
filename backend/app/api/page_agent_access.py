"""Admin endpoints for per-page agent access.

A quick-toggle layer over approval rules, surfaced from a page's actions menu.
For each (agent, page) the admin picks a level:

- ``default`` — no page-specific rules; the global rule chain applies.
- ``free``    — the agent's module writes on this page auto-approve.
- ``blocked`` — the agent's module writes on this page are denied.

``free``/``blocked`` are persisted as a *managed set* of ordinary approval
rules, one per module action type, scoped to exactly (agent_id, page_id) with
no module/type/ownership narrowing. Because rule matching orders by
specificity (agent+page = 2) these outrank the global built-ins (0-1) without
touching priorities, and they remain visible/editable in Settings → Rules.

Reading access back is shape-based, not marker-based: any enabled rule that
fits the managed shape counts toward the level, and anything narrower on the
same agent+page surfaces as ``custom_rule_count``. If the managed rules no
longer form a complete uniform set (e.g. one was disabled or retargeted in
the Rules UI), the level reports ``custom``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..approval import bump_rules_version
from ..auth.deps import CurrentUser, require_csrf, require_session
from ..db import get_session, read_session
from ..errors import not_found
from ..ids import new_id
from ..models import Agent, ApprovalRule, Module, Page, utcnow_iso
from ..schemas import PageAgentAccessItem, PageAgentAccessOut, PageAgentAccessSet
from ..schemas.pages import PageAgentAccessLevel
from ..services.audit import write_event

router = APIRouter(prefix="/api/v1/pages", tags=["pages"])

# The module write actions an agent can take *on a page*. fire_action_button
# targets an ActionTarget (not page-bound) and create/delete_page are about
# the page itself, so none of them belong to this per-page set. append_log
# flows through the engine as update_module_data, so it is covered.
PAGE_ACCESS_ACTION_TYPES: tuple[str, ...] = (
    "create_module",
    "update_module_data",
    "update_module_config",
    "update_module_meta",
    "delete_module",
)

_LEVEL_OUTCOME = {"free": "auto_approve", "blocked": "deny"}
_LEVEL_LABEL = {"free": "full access", "blocked": "blocked"}


def _is_managed_shape(rule: ApprovalRule) -> bool:
    """True if the rule is exactly the shape the quick toggles create."""
    return (
        not rule.is_builtin
        and rule.module_type is None
        and rule.module_id is None
        and rule.owner_scope == "any"
        and rule.action_type in PAGE_ACCESS_ACTION_TYPES
    )


def _classify(agent_page_rules: list[ApprovalRule]) -> tuple[PageAgentAccessLevel, int]:
    """Compute (access level, custom_rule_count) from an agent's rules on a page."""
    enabled = [r for r in agent_page_rules if r.enabled]
    managed = [r for r in enabled if _is_managed_shape(r)]
    custom_count = len(enabled) - len(managed)
    if not managed:
        return "default", custom_count
    outcomes = {r.outcome for r in managed}
    complete = {r.action_type for r in managed} == set(PAGE_ACCESS_ACTION_TYPES)
    if complete and outcomes == {"auto_approve"}:
        return "free", custom_count
    if complete and outcomes == {"deny"}:
        return "blocked", custom_count
    return "custom", custom_count


async def _module_counts(session: AsyncSession, page_id: str) -> dict[str, int]:
    rows = await session.execute(
        select(Module.owner_id, func.count())
        .where(
            Module.page_id == page_id,
            Module.owner_kind == "agent",
            Module.deleted_at.is_(None),
        )
        .group_by(Module.owner_id)
    )
    return {owner_id: count for owner_id, count in rows.all()}


async def _agent_page_rules(
    session: AsyncSession, page_id: str, agent_id: str
) -> list[ApprovalRule]:
    rows = await session.execute(
        select(ApprovalRule).where(
            ApprovalRule.page_id == page_id,
            ApprovalRule.agent_id == agent_id,
        )
    )
    return list(rows.scalars().all())


def _to_item(
    agent: Agent, rules: list[ApprovalRule], module_count: int
) -> PageAgentAccessItem:
    access, custom_count = _classify(rules)
    return PageAgentAccessItem(
        agent_id=agent.id,
        display_name=agent.display_name,
        status=agent.status,
        module_count=module_count,
        access=access,
        custom_rule_count=custom_count,
    )


async def _require_page(session: AsyncSession, page_id: str) -> Page:
    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is not None:
        raise not_found("page.not_found", page_id)
    return page


@router.get("/{page_id}/agent-access", response_model=PageAgentAccessOut)
async def get_page_agent_access(
    page_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> PageAgentAccessOut:
    await _require_page(session, page_id)
    agents = (
        (
            await session.execute(
                select(Agent).where(Agent.status != "revoked")
            )
        )
        .scalars()
        .all()
    )
    counts = await _module_counts(session, page_id)
    rules = (
        (
            await session.execute(
                select(ApprovalRule).where(ApprovalRule.page_id == page_id)
            )
        )
        .scalars()
        .all()
    )
    rules_by_agent: dict[str, list[ApprovalRule]] = defaultdict(list)
    for rule in rules:
        rules_by_agent[rule.agent_id].append(rule)

    items = [
        _to_item(agent, rules_by_agent.get(agent.id, []), counts.get(agent.id, 0))
        for agent in agents
    ]
    # Agents already active on the page first, then alphabetical.
    items.sort(key=lambda item: (-item.module_count, item.display_name.lower()))
    return PageAgentAccessOut(page_id=page_id, items=items)


@router.put("/{page_id}/agent-access/{agent_id}", response_model=PageAgentAccessItem)
async def set_page_agent_access(
    page_id: str,
    agent_id: str,
    body: PageAgentAccessSet,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PageAgentAccessItem:
    page = await _require_page(session, page_id)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.status == "revoked":
        raise not_found("agent.not_found", agent_id)

    # Replace the managed set wholesale: drop every managed-shape rule for
    # this agent+page (enabled or not), then recreate for the new level.
    existing = await _agent_page_rules(session, page_id, agent_id)
    removed = 0
    for rule in existing:
        if _is_managed_shape(rule):
            await session.delete(rule)
            removed += 1

    outcome = _LEVEL_OUTCOME.get(body.access)
    created = 0
    if outcome is not None:
        now = utcnow_iso()
        notes = (
            f"Page access: {_LEVEL_LABEL[body.access]} for {agent.display_name} "
            f"on '{page.name}' — managed from the page's Agent access panel"
        )
        for action_type in PAGE_ACCESS_ACTION_TYPES:
            session.add(
                ApprovalRule(
                    id=new_id("rule"),
                    agent_id=agent_id,
                    action_type=action_type,
                    module_type=None,
                    module_id=None,
                    page_id=page_id,
                    owner_scope="any",
                    outcome=outcome,
                    priority=100,
                    is_builtin=0,
                    enabled=1,
                    notes=notes,
                    created_at=now,
                    created_by=f"admin:{user.name}",
                    application_count=0,
                )
            )
            created += 1
    await session.flush()
    bump_rules_version()
    await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type="update_page_agent_access",
        target_kind="page",
        target_id=page_id,
        outcome="applied",
        payload_summary={
            "agent_id": agent_id,
            "access": body.access,
            "rules_removed": removed,
            "rules_created": created,
        },
    )

    counts = await _module_counts(session, page_id)
    rules = await _agent_page_rules(session, page_id, agent_id)
    return _to_item(agent, rules, counts.get(agent_id, 0))
