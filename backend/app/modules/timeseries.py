"""timeseries module type."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Timestamp


class _ChartType(str, Enum):
    line = "line"
    bar = "bar"
    area = "area"


class _Format(str, Enum):
    auto = "auto"
    percent = "percent"
    byte_size = "bytes"
    duration_ms = "duration_ms"


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # t = timestamp, v = value; kept terse because series carry up to 2000 points each
    t: Timestamp
    v: float


class Series(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., max_length=40)
    label: str = Field(..., max_length=80)
    color_token: str | None = None
    points: list[Point] = Field(..., max_length=2000)


class YAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    format: _Format = _Format.auto


class XAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series: list[Series] = Field(..., max_length=6)
    window_start: Timestamp | None = None
    window_end: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_type: _ChartType = _ChartType.line
    y_axis: YAxis = Field(default_factory=YAxis)
    x_axis: XAxis = Field(default_factory=XAxis)
    show_legend: bool = True
    height_px: int = Field(default=240, ge=80, le=1200)
    appearance: Appearance = Field(default_factory=Appearance)
