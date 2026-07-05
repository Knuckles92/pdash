#!/usr/bin/env bash
# Run the pdash MCP server.
#
# Required env:
#   PDASH_SERVICE_SECRET — printed by `backend/.venv/bin/python -m app.cli init`
#
# Optional env (defaults shown):
#   PDASH_BACKEND_URL=http://localhost:8080
#   PDASH_MCP_HOST=127.0.0.1
#   PDASH_MCP_PORT=8090
#   PDASH_LOG_LEVEL=INFO

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

if [[ ! -d ".venv" ]]; then
  echo "creating .venv..."
  python3.12 -m venv .venv
  .venv/bin/pip install -e .
fi

exec .venv/bin/python -m app.main
