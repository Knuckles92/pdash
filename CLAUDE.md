# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**pdash** is a self-hosted, single-admin personal command center and AI-agent integration surface. AI agents (via MCP) propose changes to a dashboard of "modules"; every agent write flows through an **approval engine** that auto-approves, denies, or queues it for the admin to decide in the web UI. Tailscale-only — never exposed to the public internet. Single admin, single tenant, single-writer SQLite, homelab-scale.

`PLAN.md` is the authoritative design + roadmap and is referenced throughout the code as `PLAN §N`. When code comments cite a section, that's the spec — read it before changing behavior.

## Three services

| Service | Stack | Dev port | Role |
|---|---|---|---|
| `backend/` | FastAPI + async SQLAlchemy + SQLite (WAL) | 8080 | Source of truth. All business logic, approval engine, auth, SSE. |
| `mcp/` | FastMCP (streamable-HTTP) | 8090 (`/mcp`) | **Thin** translator: MCP tool calls → `POST /api/v1/internal/*` HTTP. Holds almost no logic. |
| `frontend/` | Next.js 15 App Router + React 19 + Tailwind v4 | 3000 | Admin web UI. |
| `screenshot/` | FastAPI + Playwright (headless Chromium) | 9000 (`/capture`) | **Optional** sidecar. Renders a live frontend page to PNG for the `screenshot_page` MCP tool. Backend-only caller; disabled when unconfigured. |

In production a Caddy reverse proxy (`Caddyfile`, `docker-compose.yml`) fronts the three core services; the screenshot sidecar (if enabled) is internal-only.

## Commands

All routine tasks go through the **root `Makefile`** (run from repo root):

```bash
make setup            # one-time: create backend/.venv + mcp/.venv, npm ci, init data/pdash.db, write PDASH_SERVICE_SECRET to .env
make dev              # run all three natively with hot reload (logs in .dev/logs/)
make dev-stop         # stop processes started by `make dev`
make test             # backend pytest + mcp pytest + frontend typecheck+build
make test-backend     # backend pytest only
make test-mcp         # mcp pytest only
make test-frontend    # cd frontend && npm run typecheck && npm run build
make prod / make build / make init / make backup / make logs   # Docker production lifecycle
```

First-time dev: `cp .env.development.example .env && make setup && make dev`, then open http://localhost:3000 (default password `dev`).

### Running a single test

```bash
cd backend && .venv/bin/pytest tests/test_modules.py::test_name -q   # backend
cd mcp     && .venv/bin/pytest tests/test_tools_propose_module.py -q  # mcp
```

Backend/MCP use their own virtualenvs — always invoke `.venv/bin/pytest` (or `.venv/bin/python -m ...`), not a global `pytest`. `pytest-asyncio` is in `auto` mode, so `async def test_*` needs no decorator. Each backend test runs against a fresh temp SQLite file; the `initialized_db` fixture runs migrations + admin bootstrap and `admin_client` returns a logged-in `TestClient` with `X-CSRF-Token` pre-wired.

### Lint / typecheck

- Backend/MCP: `ruff` (line-length 100, configured in each `pyproject.toml`). Python 3.12+.
- Frontend: `npm run lint` (eslint, next/core-web-vitals) and `npm run typecheck` (`tsc --noEmit`).

## Architecture: the request flow that matters

There are **two distinct API surfaces** on the backend, and the difference drives everything:

1. **Admin path** (`/api/v1/...`, e.g. `modules`, `pages`, `agents`, `approval_rules`) — authed by signed-cookie session + double-submit CSRF (`X-CSRF-Token` header on mutations) + progressive login throttle. The admin acts directly; writes are immediate. Served to the browser.

2. **Internal/agent path** (`/api/v1/internal/...`) — authed by `Authorization: Bearer <service_secret>` + `X-Agent-Id` header (see `api/internal_auth.py`). No CSRF (no cookies). **Every write here goes through the approval engine — agents never mutate state directly.** Per-agent read/write rate limits apply. This is the surface the MCP server calls.

The MCP server (`mcp/`) holds raw agent API keys presented by AI clients, resolves them to an `agent_id` via `POST /api/v1/internal/auth/resolve-key` (caches resolutions ~30s, see `mcp/app/decision_cache.py` / `auth.py`), then forwards tool calls as `/internal/*` requests with the standard `Bearer` + `X-Agent-Id` headers. The MCP tools live in `mcp/app/tools.py`; they map ~1:1 onto internal endpoints. Tool write responses carry `status=applied|pending|denied` — agents must **not** retry `pending`; they poll `list_my_pending_requests`.

Beyond the write/read core, agents get a **visibility + self-diagnosis** surface (all read-only, no approval engine): `whoami`, `list_module_schemas`, `validate_module` (dry-run a payload), `module_health` (which of my modules fail to render, with structured per-field errors), `render_page` (structured view of a page + ASCII layout sketch + per-module render status), `get_module`/`list_pages` (real backend endpoints — no more MCP-side scanning), and `screenshot_page` (real PNG via the screenshot sidecar; returns an MCP image). Module render-health is computed on read by re-validating stored `data`/`config` against the type's Pydantic models — there is no persisted health column. See `docs/agent_visibility.md`.

There is also a small **ungated bootstrap surface** — the only MCP tools callable with no agent key: `onboarding`, `request_registration`, `claim_registration` (in `BOOTSTRAP_TOOLS`). A keyless client requests registration; it always lands `pending` in `agent_registration_requests` for the admin to approve in Settings → Agents (never auto-minted). The `hb_agt_` key is minted only when the client claims it after approval (mint-on-claim; only a sha256 of a one-time claim token is stored). Backend routes are service-secret-only (`api/internal_bootstrap.py`), admin review is `api/agent_registrations.py`. See `docs/agent_onboarding.md`.

### Approval engine (`backend/app/approval/`)

The heart of the system. Flow for an agent write:

```
internal endpoint → orchestrator.submit_request → engine.decide → {auto_approve | deny | prompt}
   auto_approve → write ApprovalRequest as 'approved' + apply.apply_request (immediate state change)
   deny         → write as 'denied'
   prompt       → write as 'pending' with expires_at (7-day TTL); admin decides later in UI
```

- `engine.py` — rule matching. Rules are cached in-process (`dict[action_type, list[CachedRule]]`), sorted by **specificity desc → priority asc → outcome rank (deny > prompt > auto_approve) → created_at desc**; first match wins, no match → `prompt` (§7.3). Mutating rules must call `bump_rules_version()` to invalidate the cache. Nine built-in rules are seeded (PLAN §7.2).
- `orchestrator.py` — turns a decision into persisted rows + audit log + after-commit events, all inside the caller's transaction.
- `apply.py` — actually performs the approved mutation. `lifecycle.py` — status transition helpers. `expiry.py` — pending TTL. `preview.py` — dashboard preview rendering for the approval UI.
- **Per-page agent access** (`api/page_agent_access.py`) — quick-toggle layer over rules, opened from a page's `…` menu ("Agent access", `components/page/AgentAccessSheet.tsx`). `GET/PUT /api/v1/pages/{id}/agent-access[/{agent_id}]` sets `default|free|blocked` per agent by replacing a *managed set* of agent+page-scoped rules (one per module action type); levels are read back shape-based, so hand-edits in Settings → Rules surface as `custom`.

### Realtime (SSE / EventBus, `backend/app/events/`)

- `bus.py` — in-process singleton pub/sub with per-topic ring buffers (default 5min/1000; `log_stream:*` 1min/500; `approvals` 10min/2000). Non-blocking publisher; a slow subscriber gets a `resync_required` and is dropped. Supports `Last-Event-Id` replay.
- `publish.py` — **publish via `publish_after_commit(session, topic, kind, payload)`**, not directly. It defers the publish to a SQLAlchemy `after_commit` hook so SSE subscribers never see an event before the row is committed/visible (and drops it on rollback). Only use `publish_now` when there's no surrounding transaction.
- `api/events.py` — two SSE routes: `GET /api/v1/events` (admin session, broad topics) and `GET /api/v1/internal/events` (service-secret, restricted to `approvals` + `agent:<id>`). The MCP `decision_cache` subscribes to the internal feed.

### Data & persistence (`backend/app/db.py`, `models.py`)

- **Single-writer SQLite.** `get_session` opens every request transaction with `BEGIN IMMEDIATE` to grab the writer lock up front; `read_session` is read-only (no immediate begin). WAL + tuned pragmas set per-connection.
- Schema is owned by **Alembic** (`backend/alembic/versions/`), not `create_all`. Migrations run via `python -m app.cli init` (first boot) or `alembic upgrade head` (subsequent — see `docker-entrypoint.sh`). Tables/indexes/CHECK constraints mirror PLAN §3.
- IDs are prefixed ULIDs minted by `ids.new_id("mod"|"pg"|"agt"|"apr"|"rule"|"act"|"msg")`.
- Large audit/activity payloads (>32KB, configurable) spill from `activity_log` into `audit_blobs`. There's a FTS index for activity search (migration `0002`).

### Module type system (`backend/app/modules/`)

Thirteen module types (`markdown`, `key_value`, `table`, `timeseries`, `log_stream`, `link_list`, `iframe`, `action_button`, `notification`, `file`, `sticky_note`, `progress`, `html`). Each is one file exporting Pydantic `Data` + `Config` models, registered in `modules/__init__.py:REGISTRY`. `GET /api/v1/module-schemas[/{type}]` serves their JSON Schema; the frontend's hand-rolled `SchemaForm` (`components/forms/SchemaForm.tsx`) renders edit forms from that schema. `modules.schema_version` supports lazy migrate-on-read (registry deferred). When adding/changing a module type, update the Pydantic models — the schema endpoint and frontend form follow automatically.

The **corkboard** page `kind` (alongside `home`/`agent`/`custom`/`system`) renders its `sticky_note` modules as a tidy masonry of cards instead of the grid — pinned notes (`data.pinned`) float first, then newest. Each note is its own module carrying a title, a markdown body, and/or a checklist (`data.items`); the admin adds/edits/recolors/pins/deletes them inline, agents leave notes via the normal `propose_module` flow (type `sticky_note`). The board's *look* is one of several **themes** (Clean / Corkboard / Pastel / Minimal / Ruled) the admin switches live; the choice is persisted client-side per board in `localStorage`. See `lib/modules/corkboard.ts` (theme registry) + `components/page/CorkboardBoard.tsx` + `components/page/StickyNote.tsx`. (Note ordering uses recency + pin, not the old `{x,y,rotation}` free-positioning — that's gone.)

The **canvas** page `kind` renders its first `html` module full-bleed: a complete agent-authored HTML document in a sandboxed iframe (`srcdoc`, `sandbox="allow-scripts allow-popups allow-forms"`, **never** `allow-same-origin` — opaque origin, no access to the pdash session/API, so no sanitizer is needed and the approval preview is safe too). pdash injects `--pdash-*` theme tokens into `<head>` (`lib/modules/html.ts`, values mirrored from `globals.css`); the token contract is documented for agents in the `html` field description (`backend/app/modules/html.py`). Agents get a canvas via `propose_page(kind="canvas")` then `propose_module(type="html")`; a migration-seeded built-in rule makes `update_module_data` on `html` modules always **prompt** (more specific than the generic self-owned auto-approve; the admin can disable it in Settings → Rules). The `html` module also works as a normal grid tile with `config.height_px`. See `components/page/CanvasView.tsx` + `components/modules/HtmlModule.tsx`.

### Frontend (`frontend/`)

- App Router under `app/(app)/` (authed shell) + `app/login/`. `middleware.ts` redirects to `/login` without a `session` cookie.
- `lib/api.ts` — the only way to call the backend. Same-origin in the browser (Next rewrites `/api/*` → `PDASH_BACKEND_URL`, so cookies just work); on the server (RSC/route handlers) pass `cookieHeader` to forward cookies. Auto-injects `X-CSRF-Token` on mutating methods; throws typed `ApiError` from RFC 7807 problem responses.
- Module renderers in `components/modules/` (one per type, dispatched by `ModuleRenderer`); edit mode uses dnd-kit drag/reorder via `EditablePageGrid`. Approvals/rules/activity UIs under `components/{approvals,activity}` and `app/(app)/settings/`.

## Conventions

- **Errors:** backend raises `ProblemDetail` (RFC 7807, `application/problem+json`) with stable `code` strings (helpers in `app/errors.py`: `bad_request`, `unauthorized`, `forbidden`, …). Don't return ad-hoc error JSON.
- **Env vars** are all prefixed `PDASH_` and loaded via pydantic-settings from `.env` (and `../.env` for sub-services). `PDASH_SERVICE_SECRET` (shared backend↔MCP secret) is generated by `make setup`. See `backend/README.md` for the full table; `PDASH_DATABASE_PATH` overrides `PDASH_DATABASE_URL`.
- **Idempotency:** internal writes accept an idempotency key; replays are deduped via `request_idempotency` (`services/idempotency.py`, `api/_idem.py` / `_agent_idem.py`).
- **Phase markers:** the project was built in phases; look for `TODO Phase N` where a hook is wired but unimplemented. Roadmap context lives in `PLAN.md` and `docs/`.

## Docs

`docs/dev.md` (local dev), `docs/deploy.md` (Tailscale TLS + backups), `docs/agent_visibility.md` (agent read/diagnosis tools), `docs/agent_onboarding.md` (agent-first MCP registration/bootstrap), `docs/phase{4,5}_smoke.md` (manual smoke-test recipes). `PLAN.md` for the full design.
