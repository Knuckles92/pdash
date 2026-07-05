"""Bootstrap CLI: `python -m app.cli init --admin-password ...`

Creates the SQLite DB, runs migrations, stores the admin password hash,
and generates the signing + service secrets. The service secret is printed
to stdout once for later MCP server configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import secrets
import sys
from pathlib import Path

from alembic.config import Config as AlembicConfig
from sqlalchemy import text

from alembic import command

from .auth.passwords import hash_password
from .auth.secrets import KEY_ADMIN_PASSWORD, KEY_SERVICE_SECRET, KEY_SIGNING_SECRET, set_kv
from .config import get_settings
from .db import get_sessionmaker, reset_engine


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(str(_backend_root() / "alembic.ini"))
    cfg.set_main_option("script_location", str(_backend_root() / "alembic"))
    return cfg


def run_migrations() -> None:
    cfg = _alembic_config()
    command.upgrade(cfg, "head")


_ENV_SERVICE_SECRET = re.compile(r"^PDASH_SERVICE_SECRET=.*$", re.MULTILINE)


def write_service_secret_to_env(env_path: Path, service_secret: str) -> None:
    """Set or append PDASH_SERVICE_SECRET in a dotenv file."""
    key_line = f"PDASH_SERVICE_SECRET={service_secret}"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
        if _ENV_SERVICE_SECRET.search(text):
            text = _ENV_SERVICE_SECRET.sub(key_line, text)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += key_line + "\n"
        env_path.write_text(text, encoding="utf-8")
    else:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(key_line + "\n", encoding="utf-8")


async def _bootstrap_kv(admin_password: str) -> str:
    """Persist password hash + secrets. Returns the service secret in plaintext."""
    sm = get_sessionmaker()
    signing_secret = secrets.token_urlsafe(48)
    service_secret = secrets.token_urlsafe(48)
    async with sm() as session:
        await session.execute(text("BEGIN IMMEDIATE"))
        await set_kv(session, KEY_ADMIN_PASSWORD, hash_password(admin_password))
        await set_kv(session, KEY_SIGNING_SECRET, signing_secret)
        await set_kv(session, KEY_SERVICE_SECRET, service_secret)
        await session.commit()
    await reset_engine()
    return service_secret


def _print_init_banner(db_path: Path | None, *, secret_line: str) -> None:
    """Print the boxed 'pdash initialized' banner; secret_line is the middle message."""
    print("=" * 64)
    print("pdash initialized.")
    if db_path is not None:
        print(f"DB:   {db_path}")
    print(secret_line)
    print("=" * 64)


async def _init(
    admin_password: str,
    *,
    write_env: Path | None = None,
) -> None:
    settings = get_settings()
    db_path = settings.resolved_database_path()
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Alembic uses a sync driver; spawn migrations on the event loop's default executor.
    await asyncio.to_thread(run_migrations)
    service_secret = await _bootstrap_kv(admin_password)

    if write_env is not None:
        write_service_secret_to_env(write_env.resolve(), service_secret)
        _print_init_banner(
            db_path,
            secret_line=f"Wrote PDASH_SERVICE_SECRET to {write_env.resolve()}",
        )
        return

    _print_init_banner(
        db_path,
        secret_line=(
            "Service secret (store this — used by the MCP server later):\n"
            f"  {service_secret}"
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="pdash bootstrap CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Initialize the database and admin credentials")
    init.add_argument(
        "--admin-password",
        required=True,
        help="Admin password to hash with argon2id and persist in kv_settings.",
    )
    init.add_argument(
        "--write-env",
        metavar="PATH",
        type=Path,
        default=None,
        help="Write PDASH_SERVICE_SECRET into this .env file (does not print the secret).",
    )

    args = parser.parse_args(argv)
    if args.cmd == "init":
        try:
            asyncio.run(_init(args.admin_password, write_env=args.write_env))
        except Exception as exc:
            print(f"init failed: {exc}", file=sys.stderr)
            return 1
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
