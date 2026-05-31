# shellcheck shell=bash
# Source repo-root .env into the current shell (export all keys).
# Usage: source "$(dirname "$0")/load-env.sh"   # from scripts/lib/
#    or: source "$REPO_ROOT/scripts/lib/load-env.sh"

load_pdash_env() {
  local root="${1:-}"
  if [[ -z "$root" ]]; then
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  fi
  local env_file="$root/.env"
  if [[ ! -f "$env_file" ]]; then
    echo "load_pdash_env: missing $env_file (copy .env.development.example to .env)" >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  export REPO_ROOT="$root"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  load_pdash_env "${1:-}"
fi
