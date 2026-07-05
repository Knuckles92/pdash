"""progress module type — a list of named progress bars (current/target)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Icon, Severity, Timestamp


class _Density(str, Enum):
    compact = "compact"
    normal = "normal"


class _Sort(str, Enum):
    as_is = "as-is"
    percent_asc = "percent-asc"
    percent_desc = "percent-desc"
    label = "label"


class ProgressBar(BaseModel):
    """A single labeled progress bar.

    ``percent = current / target``. The renderer clamps the *fill width* to
    [0, 100]% but the text value may legitimately exceed 100% (over-goal).
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, max_length=40)
    label: str = Field(..., max_length=80)
    current: float = Field(default=0, ge=0)
    target: float = Field(..., gt=0)
    unit: str | None = Field(default=None, max_length=16)
    severity: Severity | None = None
    icon: Icon | None = None
    hint: str | None = Field(default=None, max_length=200)


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bars: list[ProgressBar] = Field(..., max_length=40)
    updated_at: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    show_values: bool = True
    show_percent: bool = True
    density: _Density = _Density.normal
    sort: _Sort = _Sort.as_is
    empty_message: str | None = Field(default=None, max_length=200)
    appearance: Appearance = Field(default_factory=Appearance)
