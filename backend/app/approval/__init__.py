"""Approval engine: rule matching, lifecycle, and apply.

Approval-engine package. Split into:

- ``engine``     — rule cache + matching + decision.
- ``lifecycle``  — explicit state machine for ``approval_requests.status``.
- ``apply``      — atomic apply of an approved request against the data model.
- ``expiry``     — sweep stale ``pending`` rows past their ``expires_at``.
"""

from .engine import Decision, RuleCache, bump_rules_version, decide, get_rule_cache
from .lifecycle import (
    InvalidTransition,
    mark_application_failed,
    mark_applied,
    mark_approved,
    mark_denied,
    mark_executed,
    mark_execution_failed,
    mark_expired,
    mark_superseded,
)

__all__ = [
    "Decision",
    "RuleCache",
    "decide",
    "bump_rules_version",
    "get_rule_cache",
    "InvalidTransition",
    "mark_approved",
    "mark_denied",
    "mark_applied",
    "mark_application_failed",
    "mark_executed",
    "mark_execution_failed",
    "mark_superseded",
    "mark_expired",
]
