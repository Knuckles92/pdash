"""table module type."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Severity, Timestamp


class _ColType(str, Enum):
    text = "text"
    number = "number"
    timestamp = "timestamp"
    severity = "severity"
    icon = "icon"
    link = "link"
    action = "action"


class _Align(str, Enum):
    left = "left"
    center = "center"
    right = "right"


class _Density(str, Enum):
    compact = "compact"
    normal = "normal"
    comfortable = "comfortable"


class _MobileLayout(str, Enum):
    scroll = "scroll"
    card_stack = "card-stack"


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., max_length=40)
    label: str = Field(..., max_length=80)
    type: _ColType
    align: _Align | None = None
    hide_on_mobile: bool = False


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: str | None = Field(default=None, max_length=80)
    severity: Severity | None = None
    # cells is a free map of col_id → scalar or richer cell object.
    cells: dict[str, Any]


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[Column] = Field(..., max_length=12)
    rows: list[Row] = Field(..., max_length=500)
    updated_at: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    empty_message: str | None = Field(default=None, max_length=200)
    row_density: _Density = _Density.normal
    mobile_layout: _MobileLayout = _MobileLayout.scroll
    default_sort: dict[str, Any] | None = None
    appearance: Appearance = Field(default_factory=Appearance)
