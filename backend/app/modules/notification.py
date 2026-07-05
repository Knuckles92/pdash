"""notification module type."""

from __future__ import annotations

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from ._common import Appearance, Icon, Severity, Timestamp


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., max_length=60)
    href: AnyUrl | None = None
    action_target_id: str | None = Field(default=None, max_length=64)


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., max_length=2000)
    severity: Severity
    created_at: Timestamp
    expires_at: Timestamp | None = None
    dismissed_at: Timestamp | None = None
    action: Action | None = None
    icon: Icon | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dismissible: bool = True
    auto_dismiss_seconds: int | None = Field(default=None, ge=1, le=86400)
    pin_to_top: bool = False
    sound: bool = False
    appearance: Appearance = Field(default_factory=Appearance)
