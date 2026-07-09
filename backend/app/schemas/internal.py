"""Schemas for the ``/api/v1/internal/*`` MCP-facing surface."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProposeModuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    page_id: str
    title: str | None = Field(default=None, max_length=200)
    position: int = 0
    grid: dict[str, Any] | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=1000)


class UpdateModulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    title: str | None = Field(default=None, max_length=200)
    position: int | None = None
    page_id: str | None = None


class UpdateModuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    patch: UpdateModulePatch
    rationale: str | None = Field(default=None, max_length=1000)
    expected_etag: str | None = None


class DeleteModuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rationale: str | None = Field(default=None, max_length=1000)
    expected_etag: str | None = None


class LogLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: str | None = None
    level: str | None = None
    message: str = Field(..., max_length=2000)
    fields: dict[str, Any] | None = None


class AppendLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    lines: list[LogLine] = Field(..., min_length=1, max_length=200)
    rationale: str | None = Field(default=None, max_length=1000)


class FireActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: str
    payload: dict[str, Any] | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class ProposePageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,40}$")
    description: str | None = Field(default=None, max_length=500)
    type: Literal["agent", "canvas"] = "agent"
    rationale: str | None = Field(default=None, max_length=1000)


class RegisterFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbox_name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=200)
    page_id: str | None = None
    purpose: str | None = Field(default=None, max_length=1000)
    rationale: str | None = Field(default=None, max_length=1000)


class FileDropboxPage(BaseModel):
    page_id: str
    slug: str
    name: str
    drop_path: str


class FileDropboxOut(BaseModel):
    inbox_root: str
    target: str | None = None
    pages: list[FileDropboxPage] = Field(default_factory=list)
    max_bytes: int
    mime_allowlist: list[str] = Field(default_factory=list)
    guidance: str


class ValidateModuleIn(BaseModel):
    """Dry-run validation of a proposed module payload (no write)."""

    model_config = ConfigDict(extra="forbid")

    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class WhoAmIOut(BaseModel):
    agent: dict[str, Any]
