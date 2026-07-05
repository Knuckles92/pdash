"""Shared pytest fixtures.

Each test gets a fresh SQLite DB at a temp path, with all migrations applied,
plus a TestClient pre-authenticated as the admin.
"""

from __future__ import annotations

import os
import secrets
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# Ensure the backend root is on sys.path when pytest runs from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Also expose the tests dir so test modules can import shared helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    tmpdir = tempfile.mkdtemp(prefix="pdash-test-")
    db_path = Path(tmpdir) / "test.db"
    yield db_path
    # Cleanup
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    try:
        Path(tmpdir).rmdir()
    except OSError:
        pass


@pytest.fixture
def signing_secret() -> str:
    return secrets.token_urlsafe(48)


@pytest.fixture
def initialized_db(temp_db_path: Path, signing_secret: str, monkeypatch: pytest.MonkeyPatch):
    """Apply migrations + bootstrap KV. Returns (db_path, admin_password)."""
    admin_password = "test1234"
    monkeypatch.setenv("PDASH_DATABASE_PATH", str(temp_db_path))
    monkeypatch.setenv("PDASH_SIGNING_SECRET_OVERRIDE", signing_secret)
    # Reset cached settings + engine to pick up the new env.
    from app import config as cfg
    from app import db as dbmod

    cfg.reset_settings_cache()

    import asyncio

    async def _bootstrap():
        # Force a fresh engine using the new DB path.
        await dbmod.reset_engine()
        from app.cli import run_migrations
        from app.auth.passwords import hash_password
        from app.auth.secrets import (
            KEY_ADMIN_PASSWORD,
            KEY_SERVICE_SECRET,
            KEY_SIGNING_SECRET,
            set_kv,
        )

        await asyncio.to_thread(run_migrations)
        sm = dbmod.get_sessionmaker()
        from sqlalchemy import text as sql_text

        async with sm() as session:
            await session.execute(sql_text("BEGIN IMMEDIATE"))
            await set_kv(session, KEY_ADMIN_PASSWORD, hash_password(admin_password))
            await set_kv(session, KEY_SIGNING_SECRET, signing_secret)
            await set_kv(session, KEY_SERVICE_SECRET, secrets.token_urlsafe(48))
            await session.commit()
        await dbmod.reset_engine()

    asyncio.run(_bootstrap())
    yield temp_db_path, admin_password
    # Tear down the cached engine so the next test starts clean.
    asyncio.run(dbmod.reset_engine())
    cfg.reset_settings_cache()


@pytest.fixture
def client(initialized_db) -> Generator[TestClient, None, None]:
    """A logged-out TestClient bound to the freshly-initialized DB."""
    from app.auth import throttle
    throttle.reset_all()
    from app.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_client(client: TestClient, initialized_db) -> TestClient:
    """A TestClient that is already logged in and has CSRF wired into its headers."""
    _, password = initialized_db
    resp = client.post("/api/v1/auth/login", json={"password": password})
    assert resp.status_code == 200, resp.text
    csrf = client.cookies.get("csrf_token")
    assert csrf, "csrf cookie not set after login"
    client.headers.update({"X-CSRF-Token": csrf})
    return client
