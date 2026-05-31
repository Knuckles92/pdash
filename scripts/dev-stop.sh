#!/usr/bin/env bash
# Stop processes started by scripts/dev.sh (via .dev/pids).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$REPO_ROOT/.dev/pids"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No .dev/pids file — dev stack may not be running."
  exit 0
fi

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  name="${line%%=*}"
  pid="${line#*=}"
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name (pid $pid)"
    kill "$pid" 2>/dev/null || true
  fi
done <"$PID_FILE"

rm -f "$PID_FILE"
echo "Done."
