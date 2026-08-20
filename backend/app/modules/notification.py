"""notification module type."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, HttpOrMailtoUrl, Icon, Severity, Timestamp


class Action(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str = Field(..., max_length=60)
    href: HttpOrMailtoUrl | None = None
    action_target_id: str | None = Field(default=None, max_length=64)


class Data(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(..., max_length=2000)
    severity: Severity
    created_at: Timestamp
    expires_at: Timestamp | None = None
    dismissed_at: Timestamp | None = None
    action: Action | None = None
    icon: Icon | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dismissible: bool = True
    auto_dismiss_seconds: int | None = Field(default=None, ge=1, le=86400)
    pin_to_top: bool = False
    sound: bool = False
    appearance: Appearance = Field(default_factory=Appearance)
