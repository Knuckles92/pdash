"""link_list module type."""

from __future__ import annotations

from enum import Enum

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from ._common import Appearance, Icon, Severity, Timestamp


class _Layout(str, Enum):
    list = "list"
    grid = "grid"
    chips = "chips"


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., max_length=120)
    href: AnyUrl
    description: str | None = Field(default=None, max_length=300)
    icon: Icon | None = None
    severity: Severity | None = None
    external: bool | None = None


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    links: list[Link] = Field(..., max_length=50)
    updated_at: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: _Layout = _Layout.list
    show_descriptions: bool = True
    show_icons: bool = True
    open_in_new_tab: bool = True
    appearance: Appearance = Field(default_factory=Appearance)
