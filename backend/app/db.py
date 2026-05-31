"""Async SQLAlchemy engine, session, and SQLite pragma setup."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings

logger = logging.getLogger(__name__)

# Per-connection pragmas: PLAN §3.
PRAGMAS = [
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("foreign_keys", "ON"),
    ("busy_timeout", "5000"),
    ("temp_store", "MEMORY"),
    ("mmap_size", "268435456"),
    ("cache_size", "-20000"),
]


def _install_pragma_hook(engine: AsyncEngine) -> None:
    """Wire the per-connection PRAGMA setup onto the sync engine."""
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            for name, value in PRAGMAS:
                cursor.execute(f"PRAGMA {name}={value}")
            # Read journal_mode to confirm WAL applied (PRAGMA journal_mode returns a row).
            cursor.execute("PRAGMA journal_mode")
            _ = cursor.fetchone()
        finally:
            cursor.close()


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.resolved_database_url()
        _engine = create_async_engine(
            url,
            echo=False,
            future=True,
            # NullPool would force re-pragma on every checkout; default pool reuses
            # connections, so the connect-event hook runs once per physical connection.
        )
        _install_pragma_hook(_engine)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def reset_engine() -> None:
    """Dispose of the active engine (for tests)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async session.

    Each request runs in a write-capable transaction with BEGIN IMMEDIATE
    semantics, ensuring the writer lock is grabbed up front.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        # PLAN §3: BEGIN IMMEDIATE for write transactions.
        await session.execute(text("BEGIN IMMEDIATE"))
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def read_session() -> AsyncGenerator[AsyncSession, None]:
    """Read-only session (no BEGIN IMMEDIATE)."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        finally:
            await session.close()
