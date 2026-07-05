"""Approval engine — rule cache + matching + decision.

Implements PLAN §7.1 exactly.

The rule cache is an in-process singleton. It is populated lazily on the first
call to :func:`decide` and refreshed when ``rules_version`` (an integer bumped
by rule CRUD) advances. The cache structure is
``dict[action_type, list[CachedRule]]`` sorted by specificity score desc,
then priority asc, then ``created_at`` desc.

Specificity score = number of non-wildcard scope dimensions (module_id,
page_id, module_type, agent_id) + a bit for ``owner_scope in {self, other}``
(i.e. anything other than ``any``).

Per-request matching is the linear scan from the pseudocode in §7.1; the
first hit wins (because the list is pre-sorted, more specific rules come
first). If no rule matches, the engine returns ``prompt`` per §7.3.

Tiebreakers:
- Higher specificity wins (already encoded in sort order).
- At equal specificity, lower priority wins (lower number = higher precedence).
- At equal specificity and priority, ``deny`` beats ``auto_approve`` — encoded
  via a secondary key in the sort tuple (outcome rank 0 for deny, 1 for prompt,
  2 for auto_approve so deny sorts before auto_approve at the same tier).
- At equal specificity + priority + outcome class, newer ``created_at`` wins.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ApprovalRule

DecisionStatus = Literal["auto_approve", "deny", "prompt"]


# ---------------------------------------------------------------------------
# Rule cache singleton
# ---------------------------------------------------------------------------


@dataclass
class CachedRule:
    """In-memory snapshot of an enabled rule for fast matching."""

    id: str
    agent_id: str  # "*" or a concrete agent id
    action_type: str
    module_type: str | None  # None means "N/A", "*" means "any concrete value"
    module_id: str | None
    page_id: str | None
    owner_scope: str  # any|self|other
    outcome: DecisionStatus
    priority: int
    is_builtin: bool
    created_at: str

    @property
    def specificity(self) -> int:
        score = 0
        # +1 for each non-wildcard scope dimension
        if self.module_id not in (None, "*"):
            score += 1
        if self.page_id not in (None, "*"):
            score += 1
        if self.module_type not in (None, "*"):
            score += 1
        if self.agent_id != "*":
            score += 1
        if self.owner_scope in ("self", "other"):
            score += 1
        return score


@dataclass
class RuleCache:
    """Singleton cache of enabled rules grouped by action_type and sorted."""

    rules_by_action: dict[str, list[CachedRule]] = field(default_factory=dict)
    loaded_version: int = -1


_rules_version: int = 0
_cache: RuleCache | None = None
_lock = asyncio.Lock()


def bump_rules_version() -> int:
    """Invalidate the in-process rule cache. Returns the new version."""
    global _rules_version, _cache
    _rules_version += 1
    _cache = None
    return _rules_version


def current_rules_version() -> int:
    return _rules_version


def reset_cache_for_tests() -> None:
    """Test helper: drop the cache so the next call reloads from the DB."""
    global _rules_version, _cache
    _rules_version = 0
    _cache = None


def _outcome_rank(outcome: str) -> int:
    # deny beats auto_approve at equal specificity (PLAN §7.1).
    # prompt sits in between (so a prompt rule overrides an equally-specific
    # auto_approve — admins explicitly chose to gate it).
    return {"deny": 0, "prompt": 1, "auto_approve": 2}.get(outcome, 9)


async def _load_cache(session: AsyncSession) -> RuleCache:
    """Reload the rule cache from disk; called when the version advances."""
    rows = (
        await session.execute(
            select(ApprovalRule).where(ApprovalRule.enabled == 1)
        )
    ).scalars().all()

    cache = RuleCache(loaded_version=_rules_version)
    for row in rows:
        cached_rule = CachedRule(
            id=row.id,
            agent_id=row.agent_id,
            action_type=row.action_type,
            module_type=row.module_type,
            module_id=row.module_id,
            page_id=row.page_id,
            owner_scope=row.owner_scope,
            outcome=row.outcome,  # type: ignore[arg-type]
            priority=row.priority,
            is_builtin=bool(row.is_builtin),
            created_at=row.created_at,
        )
        cache.rules_by_action.setdefault(cached_rule.action_type, []).append(cached_rule)

    # Sort within each action_type bucket:
    #   primary key: specificity desc (so most-specific first)
    #   secondary:   priority asc (lower priority value wins)
    #   tertiary:    outcome rank asc (deny beats auto_approve)
    #   quaternary:  created_at desc (newer wins)
    for bucket in cache.rules_by_action.values():
        bucket.sort(
            key=lambda r: (
                -r.specificity,
                r.priority,
                _outcome_rank(r.outcome),
                # created_at must sort descending (newer first) alongside the
                # ascending keys above; the _ReverseStr wrapper inverts its
                # comparison so it sorts descending within the same tuple.
                _ReverseStr(r.created_at),
            )
        )
    return cache


class _ReverseStr:
    """Helper to sort strings descending alongside ascending numeric keys."""

    __slots__ = ("s",)

    def __init__(self, s: str) -> None:
        self.s = s

    def __lt__(self, other: "_ReverseStr") -> bool:  # noqa: D401
        return self.s > other.s

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _ReverseStr) and self.s == other.s

    def __hash__(self) -> int:  # pragma: no cover
        return hash(self.s)


async def get_rule_cache(session: AsyncSession) -> RuleCache:
    """Return the rule cache, reloading lazily if invalidated."""
    global _cache
    async with _lock:
        if _cache is None or _cache.loaded_version != _rules_version:
            _cache = await _load_cache(session)
        return _cache


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


@dataclass
class DecisionRequest:
    """Input shape for the matcher — denormalized request fields."""

    action_type: str
    agent_id: str | None
    module_type: str | None = None
    module_id: str | None = None
    page_id: str | None = None
    agent_owns_target: bool = False


@dataclass
class Decision:
    status: DecisionStatus
    rule_id: str | None = None


def _rule_matches(rule: CachedRule, req: DecisionRequest) -> bool:
    if rule.agent_id != "*" and rule.agent_id != (req.agent_id or ""):
        return False
    if rule.module_type not in (None, "*") and rule.module_type != req.module_type:
        return False
    if rule.module_id not in (None, "*") and rule.module_id != req.module_id:
        return False
    if rule.page_id not in (None, "*") and rule.page_id != req.page_id:
        return False
    if rule.owner_scope == "self" and not req.agent_owns_target:
        return False
    if rule.owner_scope == "other" and req.agent_owns_target:
        return False
    return True


async def decide(session: AsyncSession, req: DecisionRequest) -> Decision:
    """Match a request against the rule cache and return a :class:`Decision`.

    Caller is responsible for the side effects (writing the activity log,
    flipping the request status, applying the mutation). This function is
    pure with respect to the database — it only reads through the cache.
    """
    cache = await get_rule_cache(session)
    bucket = cache.rules_by_action.get(req.action_type, [])
    for rule in bucket:
        if _rule_matches(rule, req):
            return Decision(status=rule.outcome, rule_id=rule.id)
    # PLAN §7.3 — default safe.
    return Decision(status="prompt", rule_id=None)


__all__ = [
    "CachedRule",
    "Decision",
    "DecisionRequest",
    "DecisionStatus",
    "RuleCache",
    "bump_rules_version",
    "current_rules_version",
    "decide",
    "get_rule_cache",
    "reset_cache_for_tests",
]
