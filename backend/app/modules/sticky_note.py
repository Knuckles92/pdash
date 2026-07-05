"""sticky_note module type.

A single note on a corkboard page (PLAN: corkboard board). The board orders notes
pinned-first then newest (``data.pinned`` + ``created_at``); ``data`` / ``config``
carry the note's content and look.

A note can hold a title, a markdown body, and/or a checklist of items — all
optional, so a note may be a one-liner, a formatted blurb, a to-do list, or any
mix. ``done`` strikes the whole note; ``pinned`` floats it to the top.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ._common import Appearance, Timestamp


class NoteColor(str, Enum):
    yellow = "yellow"
    pink = "pink"
    blue = "blue"
    green = "green"
    orange = "orange"
    purple = "purple"
    white = "white"


class PinStyle(str, Enum):
    pin = "pin"
    tape = "tape"
    none = "none"


class NoteFont(str, Enum):
    hand = "hand"
    normal = "normal"


class ChecklistItem(BaseModel):
    """One row of a note's checklist."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=500)
    done: bool = False


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=4000)
    items: list[ChecklistItem] = Field(default_factory=list, max_length=100)
    done: bool = False
    pinned: bool = False
    created_at: Timestamp | None = None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: NoteColor = NoteColor.yellow
    pin_style: PinStyle = PinStyle.pin
    # Legible sans is the default; "hand" is an explicit per-note opt-in that the
    # frontend themes may honor where it suits the look.
    font: NoteFont = NoteFont.normal
    appearance: Appearance = Field(default_factory=Appearance)
