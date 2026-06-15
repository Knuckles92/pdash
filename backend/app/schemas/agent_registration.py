"""Schemas for agent self-registration (agent-first MCP onboarding).

Two surfaces share these:

- The ungated bootstrap surface (``api/internal_bootstrap.py``) — service-secret
  only, called by the MCP server on behalf of a keyless client. ``Bootstrap*``.
- The admin review surface (``api/agent_registrations.py``) — session + CSRF.
  ``AgentRegistration*`` / ``Registration*``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---- bootstrap (service-secret, keyless client) ----------------------------


class BootstrapRegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    rationale: str | None = Field(default=None, max_length=1000)
    # Free-form hint about the requesting client (e.g. "Claude Code on host X").
    client_hint: str | None = Field(default=None, max_length=200)


class BootstrapRegisterOut(BaseModel):
    registration_id: str
    claim_token: str  # plaintext, shown to the requesting client ONCE
    status: str
    expires_at: str | None = None


class BootstrapClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_token: str = Field(..., min_length=8, max_length=200)
    registration_id: str | None = None


class BootstrapClaimOut(BaseModel):
    """Poll result. ``status`` is pending|approved|denied|expired|claimed.

    ``api_key`` is present only on the first ``approved`` poll (mint-on-claim);
    it is shown exactly once.
    """

    status: str
    registration_id: str | None = None
    api_key: str | None = None
    agent_id: str | None = None
    display_name: str | None = None
    reason: str | None = None
    expires_at: str | None = None


# ---- admin review ----------------------------------------------------------


class AgentRegistrationOut(BaseModel):
    id: str
    requested_name: str
    description: str | None = None
    rationale: str | None = None
    client_hint: str | None = None
    status: str
    agent_id: str | None = None
    permissions: dict[str, Any] | None = None
    created_at: str
    decided_at: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    claimed_at: str | None = None
    expires_at: str | None = None


class AgentRegistrationListOut(BaseModel):
    items: list[AgentRegistrationOut]


class RegistrationApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional admin overrides applied to the agent minted on claim.
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permissions: dict[str, Any] | None = None


class RegistrationDenyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)
