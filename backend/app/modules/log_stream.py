"""log_stream module type."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Icon, Severity, Timestamp


class _Order(str, Enum):
    newest_first = "newest-first"
    oldest_first = "oldest-first"


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: Timestamp
    message: str = Field(..., max_length=2000)
    severity: Severity | None = None
    source: str | None = Field(default=None, max_length=120)
    icon: Icon | None = None


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[Entry] = Field(..., max_length=1000)
    last_appended_at: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ring_buffer_size: int = Field(default=200, ge=20, le=1000)
    order: _Order = _Order.newest_first
    default_filter_severity: Severity | None = None
    show_source: bool = True
    monospace: bool = True
    appearance: Appearance = Field(default_factory=Appearance)
