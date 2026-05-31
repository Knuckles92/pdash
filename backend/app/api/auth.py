"""Auth endpoints: /login, /logout, /me."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    clear_session_cookies,
    current_user,
    get_admin_password_hash,
    get_signing_secret,
    issue_session_cookies,
    throttle,
    verify_password,
)
from ..auth.deps import CurrentUser
from ..db import get_session
from ..errors import unauthorized
from ..schemas import LoginIn, MeOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login(
    body: LoginIn,
    response: Response,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    key = request.client.host if request.client else "anon"
    await throttle.await_delay(key)

    stored = await get_admin_password_hash(session)
    if not stored:
        # No bootstrap yet — refuse instead of accepting anything.
        raise unauthorized("auth.not_initialized", "Admin not initialized")

    if not verify_password(stored, body.password):
        throttle.record_failure(key)
        raise unauthorized("auth.invalid_credentials", "Invalid credentials")

    throttle.reset(key)
    secret = await get_signing_secret(session)
    issue_session_cookies(response, user_id="admin", secret=secret)
    return {"user": {"user_id": "admin", "kind": "user", "name": "admin"}}


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    clear_session_cookies(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
async def me(user: Annotated[CurrentUser, Depends(current_user)]) -> MeOut:
    return MeOut(user_id=user.user_id, kind="user", name=user.name)
