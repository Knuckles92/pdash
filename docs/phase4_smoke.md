# Phase 4 — Manual Smoke Checklist

Run after `docker compose up` (or local dev start) with a fresh admin session.
Estimated 10 minutes.

## Prereqs

- Admin signed in.
- One agent registered (Settings → Agents).
- Backend tests + frontend build clean (`cd backend && .venv/bin/pytest`,
  `cd frontend && npm run build`).

## Renderers

### Timeseries
1. Home → Edit → Add module → **Timeseries (chart)**.
2. In the data form, add two series with 5–10 points each:
   - Series A: id=`cpu`, label=`CPU%`, color_token=`sky`,
     points: a small ramp of `{t: now-5m, v: …}` values.
   - Series B: id=`mem`, label=`Mem%`, color_token=`emerald`, similar shape.
3. Config: chart_type=`line`, height_px=240, y_axis.format=`percent`.
4. Save → exit edit mode → chart renders, legend visible, tooltip shows
   formatted timestamp + percent values, lines have gaps for any null points.
5. Re-edit, change chart_type to `bar`, then `area`. Both render.

### Log stream
1. Add → **Log stream**. Seed 4–5 entries via the form
   (severities: info / warning / error). Save.
2. View mode: entries render with severity dot, relative timestamps,
   monospace text, source chips.
3. Filter dropdown: pick `warning` — only warning + worse remain.
4. Add another entry via PATCH-by-edit (or via MCP append_log if wired) —
   when at the bottom (oldest-first mode) view stays pinned; scroll up
   and the "N new entries" pill appears.

### Iframe
1. Settings → **Iframe allowlist** → Add host `*.example.com` (or your test host).
2. Home → Add → **Iframe**. data.src=`https://www.example.com/`,
   title=`Example`.
3. Save → renders an iframe with chrome (open-in-new-tab link visible).
4. Now remove the allowlist entry → reload home → the iframe module shows
   the "Iframe blocked: host not allowlisted" banner.

### Notification (with pin_to_top)
1. Add → **Notification**. message=`Build succeeded`, severity=`success`,
   created_at=now. config: dismissible=true, pin_to_top=true.
2. Save. Notification renders at the *top* of the home grid, before all other
   modules, with a green left border + check icon.
3. Click dismiss (X) → optimistic hide; the module reappears empty
   (dismissed_at set). Refresh to confirm persistence.
4. Add another notification with `auto_dismiss_seconds: 5`. It vanishes
   after ~5s.

### Action button
1. Settings → **Action targets** → Webhooks tab → New webhook.
   config: `{"url": "https://httpbin.org/anything", "method": "POST"}` (or
   any reachable URL). mode=`sync`.
2. Hit the *Play* button on the row to confirm /test responds OK.
3. Home → Add → **Action button**. data.label=`Run`,
   data.action_target_id=(select the target you just made),
   config.confirm=true, style=`primary`.
4. Save → click the button → confirm dialog → confirms → toast =
   "Action fired", `last_result` panel renders below the button with
   success colors + timestamp.
5. Edit the webhook target to point at `http://127.0.0.1:1/` (refused).
   Fire again → last_result shows red "Failed" with the error.
6. Edit module config to add `cooldown_seconds: 5`. Fire → button is
   disabled with countdown for 5s.

## Backend dispatcher sanity

The `mcp_tool` and `agent_message` paths are covered by:

- `tests/test_dispatcher_mcp_tool.py`
- `tests/test_dispatcher_agent_message.py`

For a real `mcp_tool` smoke, point at any reachable streamable-HTTP MCP server
and:

```bash
# 1. create target
curl -X POST /api/v1/action-targets -d '{
  "name":"hass-toggle",
  "kind":"mcp_tool",
  "config":{
    "url":"https://hass.lan/mcp",
    "tool_name":"homeassistant.turn_on",
    "auth":{"kind":"bearer","secret_ref":"main"}
  }
}'

# 2. seed the secret
sqlite3 pdash.db "INSERT INTO kv_settings VALUES('action_target_secret:<id>:main','<token>')"

# 3. fire via action_button as above.
```

## Sign-off

- [ ] All five renderers visible on home page simultaneously.
- [ ] Iframe blocked banner appears for unlisted hosts.
- [ ] Notification pin_to_top ordering correct.
- [ ] Action button confirm + cooldown + last_result all work.
- [ ] Settings → Iframe allowlist + Action targets pages reachable from
      the Settings tab bar.
