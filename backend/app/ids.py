"""ULID-based ID generation with type prefixes."""

from __future__ import annotations

from typing import Literal

from ulid import ULID

PREFIXES = {
    "mod": "mod_",
    "pg": "pg_",
    "agt": "agt_",
    "areg": "areg_",
    "apr": "apr_",
    "rule": "rule_",
    "act": "act_",
    "msg": "msg_",
    "job": "job_",
    "fil": "fil_",
}

IdKind = Literal["mod", "pg", "agt", "areg", "apr", "rule", "act", "msg", "job", "fil"]


def new_id(kind: IdKind) -> str:
    """Return a fresh prefixed ULID string."""
    if kind not in PREFIXES:
        raise ValueError(f"Unknown ID kind: {kind}")
    return f"{PREFIXES[kind]}{ULID()}"
