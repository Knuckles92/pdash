#!/usr/bin/env bash
# Stop processes started by scripts/dev.sh (via .dev/pids), plus any orphans
# still holding a dev port.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/dev-procs.sh
source "$REPO_ROOT/scripts/lib/dev-procs.sh"

stop_dev_stack "$REPO_ROOT/.dev/pids"
echo "Done."
