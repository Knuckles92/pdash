"""Alembic environment.

Synchronous SQLite-driven env. The application uses an async engine at runtime,
but Alembic operates on a sync URL derived from the configured PDASH_DATABASE_*
env vars (falling back to alembic.ini's sqlalchemy.url).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolved_url() -> str:
    settings = get_settings()
    # Prefer the runtime-resolved path so dev/test agree.
    url = settings.resolved_database_url()
    # Alembic uses a sync driver. Strip the `+aiosqlite` part.
    return url.replace("sqlite+aiosqlite://", "sqlite://")


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = _resolved_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _resolved_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Run migrations with FK enforcement OFF. SQLite can only change a CHECK
        # constraint (or many other column edits) via a full table rebuild, and
        # `op.batch_alter_table(recreate=...)` does that by renaming/dropping the
        # table — which would cascade-delete child rows of any parent table being
        # rebuilt (e.g. `modules`/`files` under `pages`). The pragma must be set
        # outside a transaction to take effect, which is the case here (before
        # `context.begin_transaction()`). The running app still enforces FKs: it
        # sets `PRAGMA foreign_keys=ON` per connection (see app/db.py).
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA busy_timeout=30000")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            transactional_ddl=False,
        )
        with context.begin_transaction():
            context.run_migrations()
        # Belt-and-suspenders: SA 2.0 auto-rolls back un-committed work when the
        # connection closes; force a commit here in case Alembic's
        # `transactional_ddl=False` left an open transaction with our
        # bulk_insert rows pending.
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
