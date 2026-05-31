# Phase 5 — Realtime Smoke Checklist

Verify SSE wire-up across backend + frontend + MCP. ~10 minutes with a single
laptop running the full stack.

## Prereqs

- Full stack running: `make setup` (once), then `make dev` from the repo root.
- Admin signed in at [http://localhost:3000](http://localhost:3000).
- One agent registered with a freshly minted API key (`hb_agt_…`).

## A. Pending-badge live update across two tabs

1. Open `/approvals` in **two browser tabs** (same admin session).
2. In a third terminal, propose a module as the agent via the MCP server.
   Cleanest path: call the MCP `propose_module` tool through any MCP-aware
   client (Claude Desktop, mcp-cli, etc.) pointed at `http://127.0.0.1:8090/mcp`
   with `Authorization: Bearer hb_agt_…`. Alternatively, hit the backend's
   internal endpoint directly:
   ```sh
   curl -i -X POST http://127.0.0.1:8080/api/v1/internal/propose-module \
     -H "Authorization: Bearer $PDASH_SERVICE_SECRET" \
     -H "X-Agent-Id: $AGENT_ID" \
     -H "Idempotency-Key: smoke-$RANDOM" \
     -H "Content-Type: application/json" \
     -d '{"type":"markdown","page_id":"<home_page_id>","data":{"body":"hi"},"config":{}}'
   ```
   Expect HTTP 202 with `request_id`.
3. **Both tabs should show the new pending row within ~1 second** without
   reloading. The Approvals badge in the sidebar increments.

## B. Approve in tab A; tab B + home update

1. In tab A, approve the row (single-click `Approve`).
2. Tab B's list should remove the row within ~1 second; the badge decrements
   in both tabs.
3. Open `/` (home) in a third tab — the newly approved module should appear
   on the home page without refresh, with a brief ring pulse around its card.

## C. Activity "N new" pill

1. Open `/activity` in a fourth tab.
2. From the agent, fire two more proposals (any state-changing call).
3. The activity list shows a sticky "N new entries — show" pill at the top.
   Clicking it refetches and clears the counter.

## D. Log stream tail

1. Add a `log_stream` module to home (admin path) owned by your agent.
2. Open home page in a tab.
3. Have the agent call MCP `append_log` with a fresh entry.
4. The log_stream module appends the new line in place, without refresh.

## E. Reconnect / `Last-Event-Id`

1. With at least one tab on `/approvals`, kill the backend
   (`Ctrl-C` on uvicorn).
2. Within ~5s the bottom-right "reconnecting…" pill appears.
3. Restart the backend.
4. The pill disappears; the tab continues to receive new events. The browser
   automatically sent `Last-Event-Id`; check the backend logs to see the
   replay range. If the buffer expired, the server emitted
   `event: resync_required` and the tab refetched.

## F. MCP decision cache

1. With backend + MCP running, propose a module via the MCP tool — receive
   `status: "pending", request_id: ...`.
2. Within ~2 seconds, call `list_my_pending_requests` from the MCP client.
   It should return the row from cache.
3. Approve the request via the admin UI.
4. Call `list_my_pending_requests` again with
   `status_filter="pending,applied"`. The row's status should be `applied`
   reflecting the SSE push.

## G. Done criteria

- [ ] Pending badge updates live in both tabs.
- [ ] Module appears on home page on approval without refresh.
- [ ] Activity pill counts new entries without prepending them.
- [ ] log_stream tails new entries.
- [ ] Reconnect indicator appears on backend down, disappears on recovery.
- [ ] MCP decision cache observes admin approvals within ~2 s.

No remaining `# TODO Phase 5` markers in source after this exercise.
