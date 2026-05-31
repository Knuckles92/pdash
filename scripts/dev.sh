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
: >"$PID_FILE"

PIDS=()
cleanup() {
  local pid
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting pdash dev stack (logs in $LOG_DIR/)"
echo ""

(
  cd "$REPO_ROOT/backend"
  export PDASH_DATABASE_PATH
  # --timeout-graceful-shutdown: don't let open SSE streams hang a --reload.
  exec .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8080 \
    --timeout-graceful-shutdown 2
) >>"$LOG_DIR/backend.log" 2>&1 &
PIDS+=($!)
echo "backend=$!" >>"$PID_FILE"

(
  cd "$REPO_ROOT/mcp"
  export PDASH_DATABASE_PATH
  exec .venv/bin/python -m app.main
) >>"$LOG_DIR/mcp.log" 2>&1 &
PIDS+=($!)
echo "mcp=$!" >>"$PID_FILE"

(
  cd "$REPO_ROOT/frontend"
  export PDASH_BACKEND_URL="${PDASH_BACKEND_URL:-http://127.0.0.1:8080}"
  exec npm run dev
) >>"$LOG_DIR/frontend.log" 2>&1 &
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
