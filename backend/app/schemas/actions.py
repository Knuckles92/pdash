"""Action target schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionTargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    kind: str  # 'webhook'|'local_script'|'mcp_tool'|'agent_message'
    config: dict[str, Any] = Field(default_factory=dict)
    mode: str = "sync"  # 'sync'|'async' (P0)
    enabled: bool = True


class ActionTargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: dict[str, Any] | None = None
    mode: str | None = None
    enabled: bool | None = None


class ActionTargetOut(BaseModel):
    id: str
    name: str
    kind: str
    # Config is redacted in responses (secrets stripped) — see service layer.
    config: dict[str, Any]
    mode: str
    enabled: bool
    created_at: str
    deleted_at: str | None = None


class ActionTargetTestResult(BaseModel):
    ok: bool
    message: str
    details: dict[str, Any] | None = None
