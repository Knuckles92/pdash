"""action_button module type."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Icon, Severity, Timestamp


class _Style(str, Enum):
    primary = "primary"
    secondary = "secondary"
    destructive = "destructive"


class LastResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fired_at: Timestamp
    ok: bool
    message: str | None = Field(default=None, max_length=2000)
    details: dict[str, Any] | None = None


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., max_length=80)
    action_target_id: str = Field(..., max_length=64)
    icon: Icon | None = None
    severity: Severity | None = None
    disabled: bool = False
    last_result: LastResult | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = True
    confirm_text: str | None = Field(default=None, max_length=200)
    cooldown_seconds: int = Field(default=0, ge=0, le=86400)
    style: _Style = _Style.primary
    show_last_result: bool = True
    appearance: Appearance = Field(default_factory=Appearance)
