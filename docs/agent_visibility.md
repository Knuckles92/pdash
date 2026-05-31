# Agent visibility & self-service

How an AI agent (via MCP) inspects the dashboards it owns, diagnoses and fixes
broken widgets, and "sees" what a page looks like — including a real screenshot.

Everything here is **read-only** (no approval-engine involvement) except the
fixes themselves, which go through the normal `update_module` write path. All of
it is built on the internal surface (`backend/app/api/internal.py`) and exposed
as MCP tools (`mcp/app/tools.py`).

## The tools

| Tool | What it answers | Backend endpoint |
|---|---|---|
| `whoami` | Who am I, what can I do? | `GET /internal/whoami` |
| `list_pages` | What pages exist to place widgets on? | `GET /internal/pages` |
| `list_my_modules` | What modules do I own? | `GET /internal/my-modules` |
| `get_module` | Full state of one module (any owner) + `owned` + `health` | `GET /internal/modules/{id}` |
| `list_module_schemas` | What widget types exist + their schemas? | `GET /internal/module-schemas` |
| `get_module_schema` | Schema for one type | `GET /internal/module-schema/{type}` |
| `validate_module` | Is this payload valid *before* I write it? | `POST /internal/validate-module` |
| `module_health` | Which of my modules are broken, and why? | `GET /internal/module-health` |
| `render_page` | Structured view + ASCII layout of a page | `GET /internal/pages/{id}/render` |
| `screenshot_page` | A real PNG of the live dashboard | `GET /internal/pages/{id}/screenshot` |

## "What does my dashboard look like?"

Two complementary answers:

1. **`render_page(page_id)`** — fast, deterministic, headless. Returns the page,
   every module in display order (any owner), each annotated with
   `health.render_ok`, plus a `layout` block with an **ASCII sketch** of the
   grid (boxes sized by colspan, `[ERROR]` on broken widgets) and
   `broken_module_ids`. This is the cheap "read the dashboard" view.

2. **`screenshot_page(page_id, viewport_width?, full_page?)`** — a real PNG of
   the rendered page (charts, theming, layout), returned as an MCP image. Use it
   to visually confirm a change. Falls back with a clear `service_unavailable`
   error if the screenshot sidecar isn't configured — call `render_page` then.

## "Is anything broken, and how do I fix it?"

There is **no persisted health column**. A module is "broken" when its stored
`data`/`config` no longer validates against its type's Pydantic schema (e.g. a
schema tightened after the data was written, or a bad hand-edit). Health is
computed on read by re-running the same validators the renderer relies on.

Fix loop:

1. `module_health(only_broken=true)` → list of broken modules, each with
   structured `errors: [{section, loc, msg, type}]`.
2. Build a corrected payload; `validate_module(type, data, config)` to confirm
   it's clean *before* writing.
3. `update_module(module_id, data=..., config=...)` to apply the fix (owner
   data-only edits typically auto-apply).

`propose_module` / `update_module` now also return those same structured errors
under `errors` on a `module.invalid_payload` (400), so a rejected write tells
you the exact offending field.

## Screenshot architecture

```
agent → MCP screenshot_page
      → backend GET /internal/pages/{id}/screenshot
          • mints a short-lived ADMIN session cookie (signed, ~120s)
          • POST {PDASH_SCREENSHOT_SERVICE_URL}/capture  {url, cookies, viewport}
      → screenshot sidecar (headless Chromium)
          • new browser context, injects the session cookie
          • navigates PDASH_FRONTEND_URL/pages/<slug> (home → "/")
          • waits for networkidle + settle, captures PNG
      ← PNG → backend → MCP Image → agent
```

Single admin, single tenant: the screenshot is rendered **as the admin**, so an
agent sees exactly what the admin sees. The sidecar runs only on the internal
docker network (no published ports) and, when `PDASH_SERVICE_SECRET` is set,
requires it as a Bearer token.

### Enabling it

`docker-compose.yml` wires it automatically: the `screenshot` service plus the
backend's `PDASH_FRONTEND_URL` / `PDASH_SCREENSHOT_SERVICE_URL`. To **disable**,
remove the `screenshot` service (the tool then returns `service_unavailable`).

For native `make dev`, the sidecar is **not** started; run it yourself and set
`PDASH_SCREENSHOT_SERVICE_URL` if you want screenshots locally:

```bash
cd screenshot && pip install . && playwright install --with-deps chromium
uvicorn app.main:app --host 0.0.0.0 --port 9000
# then in .env:  PDASH_SCREENSHOT_SERVICE_URL=http://127.0.0.1:9000
```

### Config

| Var | Default | Meaning |
|---|---|---|
| `PDASH_FRONTEND_URL` | `http://frontend:3000` | Frontend the sidecar renders. |
| `PDASH_SCREENSHOT_SERVICE_URL` | _(empty)_ | Sidecar URL; empty disables screenshots. |
| `PDASH_SCREENSHOT_TIMEOUT_SECONDS` | `30` | Backend→sidecar HTTP timeout. |
| `PDASH_SCREENSHOT_SESSION_TTL_SECONDS` | `120` | Lifetime of the minted admin cookie. |
| `PDASH_SCREENSHOT_DEFAULT_VIEWPORT_WIDTH` | `1280` | Capture width when unspecified. |

## Notes & limits

- Reads are single-tenant: an agent may read any live module/page (so it can see
  admin-owned widgets on a shared page), but `owned` tells it what it can edit
  without approval.
- `render_page`'s ASCII layout mirrors the frontend grid
  (`grid-cols-1 lg:2 xl:3`, colspan 1/2/3, pinned notifications first) but is a
  sketch, not pixels — use `screenshot_page` for fidelity.
- `iframe` modules can't be introspected (third-party content); a screenshot may
  or may not capture them depending on load. `log_stream` content is live, so a
  screenshot is a point-in-time snapshot.
