#!/usr/bin/env bash
# Run backend (reload), MCP, and Next.js dev server with one command.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DEV_DIR="$REPO_ROOT/.dev"
LOG_DIR="$DEV_DIR/logs"
PID_FILE="$DEV_DIR/pids"

# shellcheck source=scripts/lib/load-env.sh
source "$REPO_ROOT/scripts/lib/load-env.sh"
load_pdash_env "$REPO_ROOT"
# shellcheck source=scripts/lib/dev-procs.sh
source "$REPO_ROOT/scripts/lib/dev-procs.sh"

DB_PATH="${PDASH_DATABASE_PATH:-$REPO_ROOT/data/pdash.db}"
if [[ "$DB_PATH" != /* ]]; then
  DB_PATH="$REPO_ROOT/$DB_PATH"
fi
export PDASH_DATABASE_PATH="$DB_PATH"

for bin in backend/.venv/bin/uvicorn mcp/.venv/bin/python; do
  if [[ ! -x "$REPO_ROOT/$bin" ]]; then
    echo "dev: missing $bin — run 'make setup' first." >&2
    exit 1
  fi
done
if [[ ! -d frontend/node_modules ]]; then
  echo "dev: missing frontend/node_modules — run 'make setup' first." >&2
  exit 1
fi
if [[ ! -f "$DB_PATH" ]]; then
  echo "dev: database not found at $DB_PATH — run 'make setup' first." >&2
  exit 1
fi
if [[ -z "${PDASH_SERVICE_SECRET:-}" ]]; then
  echo "dev: PDASH_SERVICE_SECRET is empty in .env — run 'make setup' first." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

# Preflight: a leftover stack (or an orphaned next-server from a previous
# double-launch) holding a dev port corrupts hot reload and the React Client
# Manifest, which shows up as a page that renders with no CSS. Clear it before
# starting so we never run two stacks against the same ports / .next dir.
stop_dev_stack "$PID_FILE"

# Keep the dev DB at the latest schema. Unlike Docker (docker-entrypoint.sh) and
# first boot (`app.cli init`), native dev never otherwise runs migrations, so a
# DB left behind by an earlier checkout silently lacks any newly-added table and
# 500s the endpoints that use it (e.g. the agent-registration bootstrap surface).
# Apply pending migrations up front; set -e aborts the launch if they fail.
echo "Applying database migrations (alembic upgrade head)…"
( cd "$REPO_ROOT/backend" && .venv/bin/alembic upgrade head )
echo ""

: >"$PID_FILE"

PIDS=()
cleanup() {
  local pid
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      _kill_group "$pid"
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

start_session() {
  if command -v setsid >/dev/null 2>&1; then
    exec setsid "$@"
  else
    exec python3 "$REPO_ROOT/scripts/lib/run-in-session.py" "$@"
  fi
}

echo "Starting pdash dev stack (logs in $LOG_DIR/)"
echo ""

# Each service is launched via `setsid` so it leads its own process group. That
# lets dev-stop (and the cleanup trap) kill the whole tree by group — npm's
# next-server grandchild can't survive as an orphan holding port 3000.
export REPO_ROOT PDASH_DATABASE_PATH

# --timeout-graceful-shutdown: don't let open SSE streams hang a --reload.
start_session bash -c 'cd "$REPO_ROOT/backend" && exec .venv/bin/uvicorn app.main:app \
  --reload --host 127.0.0.1 --port 8080 --timeout-graceful-shutdown 2' \
  >>"$LOG_DIR/backend.log" 2>&1 &
PIDS+=($!)
echo "backend=$!" >>"$PID_FILE"

start_session bash -c 'cd "$REPO_ROOT/mcp" && exec .venv/bin/python -m app.main' \
  >>"$LOG_DIR/mcp.log" 2>&1 &
PIDS+=($!)
echo "mcp=$!" >>"$PID_FILE"

export PDASH_BACKEND_URL="${PDASH_BACKEND_URL:-http://127.0.0.1:8080}"
start_session bash -c 'cd "$REPO_ROOT/frontend" && exec npm run dev' \
  >>"$LOG_DIR/frontend.log" 2>&1 &
PIDS+=($!)
echo "frontend=$!" >>"$PID_FILE"

echo "  UI:       http://localhost:3000"
echo "  Backend:  http://127.0.0.1:8080/healthz"
echo "  MCP:      http://127.0.0.1:${PDASH_MCP_PORT:-8090}/mcp"
echo ""
echo "  Logs:     tail -f $LOG_DIR/*.log"
echo "  Stop:     make dev-stop   (or Ctrl+C)"
echo ""

wait
