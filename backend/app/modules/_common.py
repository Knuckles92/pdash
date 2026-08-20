"""Cross-cutting types shared by all module schemas."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import (
    AnyUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
)

MODULE_MODEL_CONFIG = ConfigDict(extra="ignore")


class ModuleModel(BaseModel):
    """Base for module Data/Config/nested payloads. Extra keys are dropped."""

    model_config = MODULE_MODEL_CONFIG


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


_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_NAMED_COLORS = {c.value for c in AppearanceColor}


class Appearance(ModuleModel):
    """Shared per-module visual treatment."""

    theme: AppearanceTheme = AppearanceTheme.default
    color: str | None = Field(default=None)

    @field_validator("color")
    @classmethod
    def _color_named_or_hex(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if value in _NAMED_COLORS:
            return value
        if _HEX_COLOR.match(value):
            return value.lower()
        raise ValueError("color must be a named token (e.g. emerald) or #RRGGBB")


def _normalize_icon(value: object) -> object:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return s
    # PascalCase / camelCase → kebab (CheckCircle → check-circle)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s)
    return s.replace("_", "-").lower()


# Lucide names, stored kebab-case. Accepts CheckCircle / check_circle too.
Icon = Annotated[
    str,
    BeforeValidator(_normalize_icon),
    StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,40}$"),
]


def _prepend_https(value: object) -> object:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return s
    lower = s.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        return s
    if "://" not in s and not lower.startswith("mailto:"):
        return "https://" + s
    return s


_URL_ADAPTER = TypeAdapter(AnyUrl)


def _as_http_https(value: object) -> AnyUrl:
    coerced = _prepend_https(value)
    url = _URL_ADAPTER.validate_python(coerced)
    scheme = (urlparse(str(url)).scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError("URL must be http or https")
    return url


def _as_http_https_mailto(value: object) -> AnyUrl:
    coerced = _prepend_https(value)
    url = _URL_ADAPTER.validate_python(coerced)
    scheme = (urlparse(str(url)).scheme or "").lower()
    if scheme not in ("http", "https", "mailto"):
        raise ValueError("URL must be http, https, or mailto")
    return url


HttpUrl = Annotated[AnyUrl, BeforeValidator(_as_http_https)]
HttpOrMailtoUrl = Annotated[AnyUrl, BeforeValidator(_as_http_https_mailto)]


def deep_merge(existing: Any, incoming: Any) -> Any:
    """Merge ``incoming`` onto ``existing``. Dicts recurse; lists/scalars replace."""
    if isinstance(existing, dict) and isinstance(incoming, dict):
        out = dict(existing)
        for key, value in incoming.items():
            if key in out:
                out[key] = deep_merge(out[key], value)
            else:
                out[key] = value
        return out
    return incoming


# RFC 3339 timestamp.  We carry it as `datetime` and serialize to ISO 8601.
Timestamp = datetime

__all__ = [
    "Appearance",
    "AppearanceColor",
    "AppearanceTheme",
    "HttpOrMailtoUrl",
    "HttpUrl",
    "Icon",
    "MODULE_MODEL_CONFIG",
    "ModuleModel",
    "Severity",
    "Timestamp",
    "deep_merge",
]
