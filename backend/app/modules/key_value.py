"""key_value module type."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Icon, Severity, Timestamp


class _Layout(str, Enum):
    stacked = "stacked"
    two_column = "two-column"
    inline_chips = "inline-chips"


class _ValueFormat(str, Enum):
    auto = "auto"
    monospace = "monospace"
    humanize_number = "humanize-number"
    humanize_bytes = "humanize-bytes"


class KeyValueField(BaseModel):
    """A single key/value field."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., max_length=80)
    value: str | float | bool | None = None
    severity: Severity | None = None
    icon: Icon | None = None
    unit: str | None = Field(default=None, max_length=16)
    hint: str | None = Field(default=None, max_length=200)


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[KeyValueField] = Field(..., max_length=40)
    updated_at: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: _Layout = _Layout.two_column
    show_icons: bool = True
    value_format: _ValueFormat = _ValueFormat.auto
    show_updated_at: bool = True
    appearance: Appearance = Field(default_factory=Appearance)
