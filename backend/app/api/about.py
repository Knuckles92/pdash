"""About / system info for the admin UI."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth.deps import CurrentUser, require_session
from ..version import app_version

router = APIRouter(prefix="/api/v1/about", tags=["about"])


class AboutOut(BaseModel):
    version: str


@router.get("", response_model=AboutOut)
async def about(_: Annotated[CurrentUser, Depends(require_session)]) -> AboutOut:
    return AboutOut(version=app_version())
