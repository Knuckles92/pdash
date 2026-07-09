"""Cross-cutting types shared by all module schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Severity(str, Enum):
    info = "info"
    success = "success"
    warning = "warning"
    error = "error"
    muted = "muted"


class AppearanceTheme(str, Enum):
    default = "default"
    tinted = "tinted"
    solid = "solid"
    outline = "outline"


class AppearanceColor(str, Enum):
    sky = "sky"
    blue = "blue"
    indigo = "indigo"
    violet = "violet"
    purple = "purple"
    fuchsia = "fuchsia"
    pink = "pink"
    rose = "rose"
    red = "red"
    orange = "orange"
    amber = "amber"
    yellow = "yellow"
    lime = "lime"
    green = "green"
    emerald = "emerald"
    teal = "teal"
    cyan = "cyan"
    gray = "gray"
    slate = "slate"
    zinc = "zinc"


class Appearance(BaseModel):
    """Shared per-module visual treatment."""

    model_config = ConfigDict(extra="forbid")

    theme: AppearanceTheme = AppearanceTheme.default
    color: AppearanceColor | None = Field(default=None)


# Lucide names in kebab-case.
Icon = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,40}$"),
]

# RFC 3339 timestamp.  We carry it as `datetime` and serialize to ISO 8601.
Timestamp = datetime

__all__ = [
    "Appearance",
    "AppearanceColor",
    "AppearanceTheme",
    "Severity",
    "Icon",
    "Timestamp",
]
