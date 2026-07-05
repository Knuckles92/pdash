"""Signed session cookies + CSRF helpers."""

from __future__ import annotations

import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from fastapi import Request, Response

from ..config import get_settings


@dataclass
class SessionPayload:
    user_id: str
    issued_at: int
    expires_at: int
    # Optional audience/purpose. None = a normal full admin browser session.
    # A scoped value (e.g. "screenshot") marks a restricted, read-only token —
    # see auth/deps.py:current_user, which refuses unsafe methods for these.
    audience: str | None = None


def _b64encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return urlsafe_b64decode(data + padding)


def sign_session(payload: SessionPayload, secret: str) -> str:
    data: dict[str, Any] = {
        "u": payload.user_id,
        "i": payload.issued_at,
        "e": payload.expires_at,
    }
    # Only include the audience key when set, so ordinary sessions keep the exact
    # same serialized form (and signature) as before — backward compatible.
    if payload.audience is not None:
        data["a"] = payload.audience
    body = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body, sha256).digest()
    return f"{_b64encode(body)}.{_b64encode(sig)}"


def verify_session(token: str, secret: str) -> SessionPayload | None:
    try:
        body_b64, sig_b64 = token.split(".")
        body = _b64decode(body_b64)
        sig = _b64decode(sig_b64)
    except Exception:
        return None
    expected = hmac.new(secret.encode("utf-8"), body, sha256).digest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        decoded = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    try:
        audience = decoded.get("a")
        payload = SessionPayload(
            user_id=str(decoded["u"]),
            issued_at=int(decoded["i"]),
            expires_at=int(decoded["e"]),
            audience=str(audience) if audience is not None else None,
        )
    except (KeyError, ValueError, TypeError):
        return None
    if payload.expires_at < int(time.time()):
        return None
    return payload


def issue_session_cookies(
    response: Response,
    *,
    user_id: str,
    secret: str,
    csrf_value: str | None = None,
) -> tuple[str, str]:
    """Set both the signed session cookie and the CSRF cookie. Returns (session_token, csrf_token)."""
    settings = get_settings()
    now = int(time.time())
    payload = SessionPayload(
        user_id=user_id,
        issued_at=now,
        expires_at=now + settings.session_lifetime_seconds,
    )
    session_token = sign_session(payload, secret)
    csrf_token = csrf_value or secrets.token_urlsafe(32)

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=settings.session_lifetime_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    # CSRF cookie is NOT HttpOnly so JS can read & echo into X-CSRF-Token header.
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.session_lifetime_seconds,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return session_token, csrf_token


def clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def read_session_cookie(request: Request) -> str | None:
    settings = get_settings()
    return request.cookies.get(settings.session_cookie_name)


def read_csrf_cookie(request: Request) -> str | None:
    settings = get_settings()
    return request.cookies.get(settings.csrf_cookie_name)
