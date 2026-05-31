"""Module schemas (admin path)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    page_id: str
    title: str | None = Field(default=None, max_length=200)
    owner_kind: str = "user"
    owner_id: str = "admin"
    position: int = 0
    grid: dict[str, Any] | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class ModulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    position: int | None = None
    grid: dict[str, Any] | None = None
    permissions: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    page_id: str | None = None


class ModuleOut(BaseModel):
    id: str
    type: str
    title: str | None = None
    owner_kind: str
    owner_id: str
    page_id: str
    position: int
    grid: dict[str, Any] | None = None
    permissions: dict[str, Any]
    data: dict[str, Any]
    config: dict[str, Any]
    schema_version: int
    version: int
    created_at: str
    updated_at: str
    last_updated_by: str
    deleted_at: str | None = None
