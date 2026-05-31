"""iframe module type."""

from __future__ import annotations

from enum import Enum

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from ._common import Appearance


class _ReferrerPolicy(str, Enum):
    no_referrer = "no-referrer"
    no_referrer_when_downgrade = "no-referrer-when-downgrade"
    origin = "origin"
    origin_when_cross_origin = "origin-when-cross-origin"
    same_origin = "same-origin"
    strict_origin = "strict-origin"
    strict_origin_when_cross_origin = "strict-origin-when-cross-origin"
    unsafe_url = "unsafe-url"


class _SandboxFlag(str, Enum):
    allow_scripts = "allow-scripts"
    allow_same_origin = "allow-same-origin"
    allow_forms = "allow-forms"
    allow_popups = "allow-popups"


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: AnyUrl
    title: str | None = Field(default=None, max_length=200)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    height_px: int = Field(default=480, ge=120, le=2000)
    mobile_height_px: int = Field(default=320, ge=120, le=2000)
    sandbox: list[_SandboxFlag] = Field(default_factory=list)
    referrer_policy: _ReferrerPolicy = _ReferrerPolicy.strict_origin_when_cross_origin
    show_chrome: bool = True
    appearance: Appearance = Field(default_factory=Appearance)
