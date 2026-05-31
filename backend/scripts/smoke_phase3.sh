#!/usr/bin/env bash
# Phase 3 manual smoke. Requires:
#   PDASH_DB_PATH    — where to place the SQLite file (default ./smoke.db)
#   PDASH_ADMIN_PASS — admin password to bootstrap (default 'smoke-pass')
#   PDASH_HOST       — base URL of the running backend (default http://127.0.0.1:8000)
#   PDASH_AGENT_KEY  — set after registration; the MCP shim's bearer to the agent (not used by HTTP smoke directly)
#   PDASH_SERVICE_SECRET — captured from `python -m app.cli init`; used in Authorization: Bearer
#   PDASH_AGENT_ID   — captured from /api/v1/agents response
#
# Drop the captured values into your env before re-running individual sections.
#
# Usage:
#   1. Cold start:
#        cd backend
#        PDASH_DATABASE_PATH=$(pwd)/smoke.db .venv/bin/python -m app.cli init --admin-password smoke-pass
#        # Note the printed service secret; export it.
#        export PDASH_SERVICE_SECRET=<from-output>
#        PDASH_DATABASE_PATH=$(pwd)/smoke.db .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
#   2. Then run this script in another shell.

set -euo pipefail

HOST=${PDASH_HOST:-http://127.0.0.1:8000}
ADMIN_PASS=${PDASH_ADMIN_PASS:-smoke-pass}
COOKIE_JAR=$(mktemp)

echo "=== 1. Login as admin -> session cookie ==="
curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  -d "{\"password\":\"$ADMIN_PASS\"}" \
  "$HOST/api/v1/auth/login" | jq .
CSRF=$(awk '/csrf_token/{print $7}' "$COOKIE_JAR")

echo "=== 2. Register an agent + capture key ==="
AGENT_JSON=$(curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' \
  -d '{"display_name":"smoke-agent"}' \
  "$HOST/api/v1/agents")
echo "$AGENT_JSON" | jq .
AGENT_ID=$(echo "$AGENT_JSON" | jq -r .agent.id)
AGENT_KEY=$(echo "$AGENT_JSON" | jq -r .api_key)
echo "AGENT_ID=$AGENT_ID"
echo "AGENT_KEY=$AGENT_KEY  (export PDASH_AGENT_KEY if you want it persisted)"

if [[ -z "${PDASH_SERVICE_SECRET:-}" ]]; then
  echo "ERROR: PDASH_SERVICE_SECRET must be set (printed by 'python -m app.cli init')." >&2
  exit 1
fi
SERVICE_SECRET=$PDASH_SERVICE_SECRET

HOME_PAGE_ID=$(curl -sS -b "$COOKIE_JAR" "$HOST/api/v1/pages" | jq -r '.items[] | select(.slug=="home") | .id')
echo "HOME_PAGE_ID=$HOME_PAGE_ID"

echo "=== 3. Agent proposes a module (expect 202 pending) ==="
PROPOSE_BODY=$(jq -n --arg pid "$HOME_PAGE_ID" '{
  type:"markdown", page_id:$pid, title:"smoke-mod",
  data:{body:"# smoke"}, config:{}
}')
R1=$(curl -sS -w '\n%{http_code}' \
  -H "Authorization: Bearer $SERVICE_SECRET" \
  -H "X-Agent-Id: $AGENT_ID" \
  -H 'Idempotency-Key: smoke-1' \
  -H 'Content-Type: application/json' \
  -d "$PROPOSE_BODY" \
  "$HOST/api/v1/internal/propose-module")
echo "$R1"
REQ_ID=$(echo "$R1" | head -n -1 | jq -r .request_id)
echo "REQ_ID=$REQ_ID"

echo "=== 4. Re-call with same key -> X-Idempotency-Replay: true ==="
curl -sS -i \
  -H "Authorization: Bearer $SERVICE_SECRET" \
  -H "X-Agent-Id: $AGENT_ID" \
  -H 'Idempotency-Key: smoke-1' \
  -H 'Content-Type: application/json' \
  -d "$PROPOSE_BODY" \
  "$HOST/api/v1/internal/propose-module" | head -20

echo "=== 5. Admin lists pending ==="
curl -sS -b "$COOKIE_JAR" "$HOST/api/v1/approval-requests?status=pending" | jq '.items | length'

echo "=== 6. Admin approves with a narrow rule (apply_to_pending=false) ==="
APPROVE_BODY=$(jq -n --arg aid "$AGENT_ID" '{
  reason:"smoke approval",
  create_rule:{
    agent_id:$aid, action_type:"create_module", module_type:"markdown",
    outcome:"auto_approve", priority:10, apply_to_pending:false
  }
}')
curl -sS -b "$COOKIE_JAR" \
  -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' \
  -d "$APPROVE_BODY" \
  "$HOST/api/v1/approval-requests/$REQ_ID/approve" | jq '{applied, rule}'

echo "=== 7. Module appears via /api/v1/modules ==="
curl -sS -b "$COOKIE_JAR" "$HOST/api/v1/modules?page_id=$HOME_PAGE_ID" | jq '.items | map({id,title,owner_id})'

echo "=== 8. Second propose -> auto-applied via new rule ==="
PROPOSE_BODY2=$(jq -n --arg pid "$HOME_PAGE_ID" '{
  type:"markdown", page_id:$pid, title:"smoke-mod-2",
  data:{body:"# smoke 2"}, config:{}
}')
curl -sS \
  -H "Authorization: Bearer $SERVICE_SECRET" \
  -H "X-Agent-Id: $AGENT_ID" \
  -H 'Idempotency-Key: smoke-2' \
  -H 'Content-Type: application/json' \
  -d "$PROPOSE_BODY2" \
  "$HOST/api/v1/internal/propose-module" | jq '{status, request_id}'

echo "=== 9. Create a log_stream + append-log (applied) ==="
LOG_MOD_JSON=$(curl -sS -b "$COOKIE_JAR" \
  -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg pid "$HOME_PAGE_ID" --arg aid "$AGENT_ID" '{
    type:"log_stream", page_id:$pid,
    data:{entries:[]}, config:{ring_buffer_size:50},
    owner_kind:"agent", owner_id:$aid
  }')" \
  "$HOST/api/v1/modules")
LOG_MOD_ID=$(echo "$LOG_MOD_JSON" | jq -r .id)
echo "LOG_MOD_ID=$LOG_MOD_ID"
curl -sS \
  -H "Authorization: Bearer $SERVICE_SECRET" \
  -H "X-Agent-Id: $AGENT_ID" \
  -H 'Idempotency-Key: smoke-log-1' \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg mid "$LOG_MOD_ID" '{
    module_id:$mid, lines:[{message:"smoke line 1",level:"info"}]
  }')" \
  "$HOST/api/v1/internal/append-log" | jq

echo "=== 10. Delete-module proposal -> denied by admin ==="
EXISTING_MOD=$(curl -sS -b "$COOKIE_JAR" "$HOST/api/v1/modules?page_id=$HOME_PAGE_ID&limit=1" | jq -r '.items[0].id')
DEL_REQ_JSON=$(curl -sS \
  -H "Authorization: Bearer $SERVICE_SECRET" \
  -H "X-Agent-Id: $AGENT_ID" \
  -H 'Idempotency-Key: smoke-del-1' \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg id "$EXISTING_MOD" '{id:$id, rationale:"smoke delete"}')" \
  "$HOST/api/v1/internal/delete-module")
echo "$DEL_REQ_JSON" | jq
DEL_REQ_ID=$(echo "$DEL_REQ_JSON" | jq -r .request_id)
curl -sS -b "$COOKIE_JAR" \
  -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' \
  -d '{"reason":"still needed"}' \
  "$HOST/api/v1/approval-requests/$DEL_REQ_ID/deny" | jq '.request.status'

rm -f "$COOKIE_JAR"
echo "=== smoke complete ==="
