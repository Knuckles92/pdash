"""kv_settings convenience helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import KVSetting

# Well-known keys.
KEY_ADMIN_PASSWORD = "admin.password_hash"
KEY_SIGNING_SECRET = "auth.signing_secret"
KEY_SERVICE_SECRET = "mcp.service_secret"


async def get_kv(session: AsyncSession, key: str) -> str | None:
    row = await session.scalar(select(KVSetting).where(KVSetting.key == key))
    return row.value if row else None


async def set_kv(session: AsyncSession, key: str, value: str) -> None:
    existing = await session.get(KVSetting, key)
    if existing is None:
        session.add(KVSetting(key=key, value=value))
    else:
        existing.value = value
    await session.flush()


async def get_admin_password_hash(session: AsyncSession) -> str | None:
    return await get_kv(session, KEY_ADMIN_PASSWORD)


async def get_signing_secret(session: AsyncSession) -> str:
    """Return the configured signing secret (env override wins for tests)."""
    settings = get_settings()
    if settings.signing_secret_override:
        return settings.signing_secret_override
    secret = await get_kv(session, KEY_SIGNING_SECRET)
    if not secret:
        raise RuntimeError(
            "Signing secret missing from kv_settings — run "
            "`python -m app.cli init` to bootstrap."
        )
    return secret
