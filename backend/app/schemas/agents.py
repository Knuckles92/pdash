"""Agent schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permissions: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permissions: dict[str, Any] | None = None


class AgentOut(BaseModel):
    id: str
    display_name: str
    description: str | None = None
    permissions: dict[str, Any]
    status: str
    created_at: str
    last_active_at: str | None = None
    last_key_rotated_at: str | None = None


class AgentKeyOut(BaseModel):
    """Returned on create/rotate. Plaintext key is shown ONCE."""

    agent: AgentOut
    api_key: str  # plaintext, e.g. "hb_agt_<base32>"
