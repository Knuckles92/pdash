# Shared helpers for starting/stopping the local dev stack.
# Sourced by scripts/dev.sh and scripts/dev-stop.sh.

# Ports the dev stack listens on. Frontend 3000, backend 8080, MCP configurable.
dev_ports() {
  printf '%s\n' 3000 8080 "${PDASH_MCP_PORT:-8090}"
}

# Kill a process and the rest of its process group (TERM, then KILL after a beat).
# dev.sh launches each service via `setsid`, so the recorded pid leads its own
# group — killing the group takes down npm/next-server grandchildren too.
_kill_group() {
  local pid="$1"
  local pgid
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  if [[ -n "$pgid" ]]; then
    kill -TERM "-$pgid" 2>/dev/null || true
  else
    kill -TERM "$pid" 2>/dev/null || true
  fi
}

# Stop the dev stack: recorded PIDs (by group) plus a port-based backstop that
# catches orphans left behind when the PID file was overwritten by a second
# `make dev`. Returns 0 always; safe to call when nothing is running.
stop_dev_stack() {
  local pid_file="$1"
  local killed=0

  if [[ -f "$pid_file" ]]; then
    local line name pid
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      name="${line%%=*}"
      pid="${line#*=}"
      if kill -0 "$pid" 2>/dev/null; then
        echo "Stopping $name (pid $pid)"
        _kill_group "$pid"
        killed=1
      fi
    done <"$pid_file"
    rm -f "$pid_file"
  fi

  # Backstop: free any orphan still holding a dev port (e.g. a next-server whose
  # launcher died and whose pid was lost from the file). fuser may list several
  # pids for one port (uvicorn's reloader + worker), so handle each separately.
  local port holders pid
  for port in $(dev_ports); do
    holders=""
    if command -v fuser >/dev/null 2>&1; then
      holders="$(fuser "$port/tcp" 2>/dev/null || true)"
    elif command -v lsof >/dev/null 2>&1; then
      holders="$(lsof -ti "tcp:$port" 2>/dev/null || true)"
    fi
    for pid in $holders; do
      [[ -z "$pid" ]] && continue
      echo "Freeing orphan on port $port (pid $pid)"
      _kill_group "$pid"
      killed=1
    done
  done

  return 0
}
