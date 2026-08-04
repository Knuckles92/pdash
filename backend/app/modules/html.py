"""html module type.

A complete agent-authored HTML document rendered in a sandboxed iframe
(srcdoc, sandbox="allow-scripts allow-popups allow-forms", never
allow-same-origin — opaque origin, no access to the pdash session or API).
Powers `canvas` pages full-bleed and is also embeddable as a grid tile.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance

_HTML_DESC = (
    "Complete HTML document (<!doctype html>...). Rendered in a sandboxed iframe with "
    "scripts, forms, and popups allowed but NO same-origin access — the document cannot "
    "reach pdash cookies, storage, or API. External network fetches (CDN scripts, images) "
    "work. pdash injects a <style> block of theme tokens into <head> that follow the "
    "admin's light/dark theme automatically; build on-theme with these CSS custom "
    "properties: --pdash-bg, --pdash-fg, --pdash-card, --pdash-muted, --pdash-muted-fg, "
    "--pdash-border, --pdash-accent, --pdash-accent-fg, --pdash-accent-soft, "
    "--pdash-danger, --pdash-warning, --pdash-success, --pdash-info, --pdash-font-sans, "
    "--pdash-font-display, --pdash-font-mono. Example: body { background: var(--pdash-bg); "
    "color: var(--pdash-fg); font-family: var(--pdash-font-sans); }"
)


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    html: str = Field(..., max_length=400_000, description=_HTML_DESC)
    title: str | None = Field(
        default=None,
        max_length=200,
        description="Accessible iframe title (defaults to the module title).",
    )


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Heights apply in grid mode only; canvas pages render full-bleed.
    height_px: int = Field(default=640, ge=120, le=3000)
    mobile_height_px: int = Field(default=480, ge=120, le=3000)
    appearance: Appearance = Field(default_factory=Appearance)
