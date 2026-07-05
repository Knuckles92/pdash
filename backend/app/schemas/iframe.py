"""Iframe allowlist schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IframeAllowlistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_pattern: str = Field(..., min_length=1, max_length=255)
    path_prefix: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=300)


class IframeAllowlistOut(BaseModel):
    id: int
    host_pattern: str
    path_prefix: str | None = None
    description: str | None = None
    added_at: str
