"""Common Pydantic schemas."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class ReorderIn(BaseModel):
    """Atomic reorder operation. Provide the full ordered list of IDs."""

    ids: list[str] = Field(..., min_length=1, max_length=500)
    # Optional scope: page_id for /modules, or unused for /pages.
    page_id: str | None = None
