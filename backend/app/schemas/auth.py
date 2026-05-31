"""Auth schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    password: str = Field(..., min_length=1, max_length=512)


class MeOut(BaseModel):
    user_id: str
    kind: str  # "user"
    name: str
