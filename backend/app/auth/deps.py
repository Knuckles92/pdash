"""FastAPI dependencies for auth + CSRF."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import read_session
from ..errors import forbidden, unauthorized
from .cookies import read_csrf_cookie, read_session_cookie, verify_session
from .secrets import get_signing_secret


@dataclass
class CurrentUser:
    user_id: str
    name: str = "admin"


# Methods a restricted (audience-scoped) session may use. Anything else is a
# state-changing request and is refused for scoped tokens.
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def current_user(
    request: Request,
    session: AsyncSession = Depends(read_session),
) -> CurrentUser:
    token = read_session_cookie(request)
    if not token:
        raise unauthorized("auth.required", "Authentication required")
    secret = await get_signing_secret(session)
    payload = verify_session(token, secret)
    if payload is None:
        raise unauthorized("auth.invalid_session", "Session invalid or expired")
    # Audience-scoped tokens (e.g. the short-lived "screenshot" session minted
    # for dashboard captures) are READ-ONLY: they may render pages but must
    # never be replayable as a full admin credential that writes/bypasses the
    # approval engine. Refuse any state-changing method.
    if payload.audience is not None and request.method.upper() not in _SAFE_METHODS:
        raise forbidden(
            "auth.read_only_session",
            "This session is read-only and cannot perform state-changing requests",
        )
    return CurrentUser(user_id=payload.user_id, name="admin")


async def require_session(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    return user


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def require_csrf(
    request: Request,
    user: CurrentUser = Depends(current_user),
) -> CurrentUser:
    """Double-submit CSRF: header must match cookie on state-changing methods.

    GET/HEAD/OPTIONS bypass; login itself bypasses (no session yet).
    """
    if request.method.upper() not in _UNSAFE_METHODS:
        return user
    header = request.headers.get("x-csrf-token")
    cookie = read_csrf_cookie(request)
    if not header or not cookie or header != cookie:
        raise forbidden("auth.csrf", "CSRF token missing or mismatched")
    return user
