#!/usr/bin/env bash
# One-shot local development bootstrap: venvs, npm, DB init, service secret in .env.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_EXAMPLE="$REPO_ROOT/.env.development.example"
ENV_FILE="$REPO_ROOT/.env"
DB_PATH="$REPO_ROOT/data/pdash.db"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_EXAMPLE" ]]; then
    echo "setup-dev: missing $ENV_EXAMPLE" >&2
    exit 1
  fi
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Created $ENV_FILE from .env.development.example"
fi

# shellcheck source=scripts/lib/load-env.sh
source "$REPO_ROOT/scripts/lib/load-env.sh"
load_pdash_env "$REPO_ROOT"

if [[ "${PDASH_COOKIE_SECURE:-false}" == "true" && "${PDASH_ENV:-}" != "production" ]]; then
  echo "setup-dev: refusing to run with PDASH_COOKIE_SECURE=true on a non-production .env." >&2
  echo "  Use .env.development.example or set PDASH_ENV=production if intentional." >&2
  exit 1
fi

export PDASH_DATABASE_PATH="$DB_PATH"
DEV_PASSWORD="${PDASH_DEV_ADMIN_PASSWORD:-dev}"

echo "==> Python venv: backend"
if [[ ! -d backend/.venv ]]; then
  python3.12 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -U pip
(cd backend && .venv/bin/pip install -q -e ".[dev]")

echo "==> Python venv: mcp"
if [[ ! -d mcp/.venv ]]; then
  python3.12 -m venv mcp/.venv
fi
mcp/.venv/bin/pip install -q -U pip
(cd mcp && .venv/bin/pip install -q -e ".[dev]")

echo "==> Node: frontend"
if [[ -f frontend/package-lock.json ]]; then
  (cd frontend && npm ci --no-audit --no-fund)
else
  (cd frontend && npm install --no-audit --no-fund)
fi

mkdir -p data

if [[ ! -f "$DB_PATH" ]]; then
  echo "==> Initializing database at $DB_PATH"
  (cd backend && PDASH_DATABASE_PATH="$DB_PATH" \
    .venv/bin/python -m app.cli init \
      --admin-password "$DEV_PASSWORD" \
      --write-env "$ENV_FILE")
else
  echo "==> Database already exists at $DB_PATH (skipping init)"
  (cd backend && PDASH_DATABASE_PATH="$DB_PATH" .venv/bin/alembic upgrade head)
fi

# Ensure .env has absolute database path
if grep -q '^PDASH_DATABASE_PATH=' "$ENV_FILE" 2>/dev/null; then
  if [[ "$(uname -s)" == Darwin ]]; then
    sed -i '' "s|^PDASH_DATABASE_PATH=.*|PDASH_DATABASE_PATH=$DB_PATH|" "$ENV_FILE"
  else
    sed -i "s|^PDASH_DATABASE_PATH=.*|PDASH_DATABASE_PATH=$DB_PATH|" "$ENV_FILE"
  fi
else
  echo "PDASH_DATABASE_PATH=$DB_PATH" >> "$ENV_FILE"
fi

echo ""
echo "Setup complete."
echo "  Admin password: $DEV_PASSWORD"
echo "  Database:       $DB_PATH"
echo "  Next:           make dev"
