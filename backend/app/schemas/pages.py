"""Page schemas."""

from __future__ import annotations

from typing import Annotated, Literal

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


class DefaultExamplesMutationOut(BaseModel):
    cleared: int | None = None
    deployed: int | None = None


# ---------------------------------------------------------------------------
# Per-page agent access (the quick-toggle layer over approval rules)
# ---------------------------------------------------------------------------

# "custom" is read-only: it means agent+page rules exist that the quick
# toggles don't fully describe (edit them in Settings → Rules).
PageAgentAccessLevel = Literal["default", "free", "blocked", "custom"]


class PageAgentAccessItem(BaseModel):
    agent_id: str
    display_name: str
    status: str
    module_count: int
    access: PageAgentAccessLevel
    custom_rule_count: int


class PageAgentAccessOut(BaseModel):
    page_id: str
    items: list[PageAgentAccessItem]


class PageAgentAccessSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access: Literal["default", "free", "blocked"]
