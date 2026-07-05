#!/bin/sh
# Backend container entrypoint.
#
# On startup:
#  1. Ensure /data exists.
#  2. If the SQLite file is missing AND PDASH_BOOTSTRAP_ADMIN_PASSWORD is set,
#     run `python -m app.cli init` to create the DB + admin user + secrets.
#  3. Otherwise, just run Alembic upgrade head (idempotent — applies any new
#     migrations) and start the app.
#
# Set PDASH_BOOTSTRAP_ADMIN_PASSWORD only on the very first launch. Once the
# DB exists, the script will refuse to overwrite it.

set -eu

: "${PDASH_DATABASE_PATH:=/data/pdash.db}"

mkdir -p "$(dirname "$PDASH_DATABASE_PATH")"
# Agent file-drop dirs (default to siblings of the DB inside /data).
_data_dir="$(dirname "$PDASH_DATABASE_PATH")"
mkdir -p "${PDASH_FILES_INBOX_PATH:-$_data_dir/inbox}" "${PDASH_FILES_STORE_PATH:-$_data_dir/files}"

if [ ! -f "$PDASH_DATABASE_PATH" ]; then
    if [ -n "${PDASH_BOOTSTRAP_ADMIN_PASSWORD:-}" ]; then
        echo "[entrypoint] Bootstrapping pdash database at $PDASH_DATABASE_PATH"
        python -m app.cli init --admin-password "$PDASH_BOOTSTRAP_ADMIN_PASSWORD"
        unset PDASH_BOOTSTRAP_ADMIN_PASSWORD
    else
        echo "[entrypoint] DB not found at $PDASH_DATABASE_PATH and no PDASH_BOOTSTRAP_ADMIN_PASSWORD set." >&2
        echo "[entrypoint] Run once with:" >&2
        echo "  docker compose run --rm -e PDASH_BOOTSTRAP_ADMIN_PASSWORD=changeme backend /app/docker-entrypoint.sh true" >&2
        echo "or invoke 'python -m app.cli init --admin-password ...' directly." >&2
        exit 1
    fi
else
    echo "[entrypoint] Existing DB found; running migrations up to head."
    alembic upgrade head
fi

exec "$@"
