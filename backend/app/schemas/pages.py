"""Page schemas."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SlugStr = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,40}$")]


class PageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: SlugStr
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    kind: str = Field(default="custom")  # checked against allowed enum at write
    owner_kind: str | None = None
    owner_id: str | None = None


class PagePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: SlugStr | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class PageOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    kind: str
    owner_kind: str | None = None
    owner_id: str | None = None
    created_at: str
    deleted_at: str | None = None
