"""file module type — display a registered file.

``image`` files render inline; ``document`` files render a download card. The
bytes are always fetched by ``file_id`` from ``/api/v1/files/{id}/raw``; the
denormalised ``display_name``/``mime``/``size_bytes`` are a snapshot for labels.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Timestamp


class _Kind(str, Enum):
    image = "image"
    document = "document"


class _Fit(str, Enum):
    contain = "contain"
    cover = "cover"


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(..., max_length=64)
    kind: _Kind
    display_name: str = Field(..., max_length=200)
    mime: str | None = Field(default=None, max_length=120)
    alt: str | None = Field(default=None, max_length=300)
    size_bytes: int | None = Field(default=None, ge=0)
    registered_at: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_height_px: int = Field(default=480, ge=80, le=2000)
    fit: _Fit = _Fit.contain
    show_download: bool = True
    show_filename: bool = True
    appearance: Appearance = Field(default_factory=Appearance)
