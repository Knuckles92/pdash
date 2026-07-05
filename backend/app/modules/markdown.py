"""markdown module type."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Severity, Timestamp


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(..., max_length=50000)
    rendered_at: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collapsed_by_default: bool = False
    max_height_px: int = Field(default=600, ge=80, le=2000)
    callout_severity: Severity | None = None
    show_rendered_at: bool = True
    appearance: Appearance = Field(default_factory=Appearance)
