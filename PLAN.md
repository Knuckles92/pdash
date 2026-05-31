# Home Base — Build Plan (v1)

> Status: planning. No code yet. Review and revise before implementation begins.

A self-hosted personal command center and agent integration surface, served on Tailscale-only, composed of typed JSON-rendered modules and gated by a per-agent approval engine.

---

## 0. Top matter

### Hard constraints (reaffirmed)

- **Tailscale-only.** Never on the public internet. Caddy fronts the app; Tailscale is the network boundary. Auth is pragmatic: single admin session cookie for the user, per-agent API keys for the MCP server.
- **No agent-supplied code or markup.** Agents send JSON conforming to typed module schemas. The frontend is server-trusted code only. Markdown is rendered through a sanitizing renderer with no raw-HTML passthrough.
- **Every agent-initiated state change is approvable.** Admin mutations bypass approval entirely.
- **iframes are allowlisted, server-side.** Allowlist is admin-only data; agents reference allowlisted hosts, they don't add them.
- **SQLite (WAL mode) on a homelab box.** Single user, low write rate. Docker Compose, Caddy reverse proxy.
- **Modules have stable IDs.** ULID-based with type prefixes (e.g. `mod_01HZX...`).

### Tech stack (confirmed)

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, Pydantic v2, SQLite (WAL), Alembic migrations |
| MCP server | Separate Python process, official `mcp` SDK, HTTP-streamable transport |
| Frontend | Next.js (App Router), TypeScript, Tailwind, shadcn-style components, `react-markdown` + `rehype-sanitize`, dnd-kit, Recharts, Zustand for client state, `@rjsf/core` for schema-driven forms |
| Realtime | **SSE** (`sse-starlette`) — see §7 |
| Reverse proxy | Caddy |
| Deployment | Docker Compose on homelab; Tailscale serves identity |

### Repo layout (suggested)

```
pdash/
├─ backend/         # FastAPI app + Alembic migrations + module schema registry
├─ mcp/             # MCP server (thin translator over /internal)
├─ frontend/        # Next.js App Router
├─ docker-compose.yml
├─ Caddyfile
└─ docs/
```

---

## 1. Architecture

```
                ┌─────────────────────────────────────────────────────────┐
                │  Tailscale (the network boundary)                       │
                │                                                         │
   admin ──────►│  Caddy (TLS, HTTP/2)                                    │
   (browser)    │     │                                                   │
                │     ├──► Next.js (SSR + client) ──fetch──┐              │
                │     │                                    ▼              │
                │     └──► FastAPI ◄──────────────┐  /api/v1/* (session)  │
                │             │                   │                       │
                │             │ EventBus (asyncio)│                       │
                │             ▼                   │                       │
                │           SQLite (WAL)          │                       │
                │             ▲                   │                       │
                │             │                   │                       │
                │           MCP server ───────────┘  /api/v1/internal/*   │
                │             ▲                       (service token +    │
                │             │ HTTP-streamable        X-Agent-Id)        │
                │             │ (MCP transport)                           │
                └─────────────┼───────────────────────────────────────────┘
                              │
            agents (Claude Code, Claude Desktop, ChatGPT, OpenClaw, Hermes, …)
            authenticate with per-agent API keys
```

**Key flow distinctions:**

- **Admin browser path:** Next.js Server Components fetch FastAPI with the session cookie. CSRF via double-submit token for mutations. Admin writes bypass the approval engine.
- **Agent path:** Agent → MCP server (HTTP-streamable, `Authorization: Bearer <agent-api-key>`) → FastAPI `/api/v1/internal/...` (service token + `X-Agent-Id`). All writes route through the approval engine. The MCP server is a thin translation layer; no business logic.
- **Realtime:** Single SSE endpoint `/api/v1/events?topics=...` driven by an in-process `EventBus` populated by every write path. Browser subscribes; the MCP server also subscribes to `/api/v1/internal/events?topics=approvals` to keep a fresh decision cache.
- **Single SQLite file** for everything. Both Next.js and MCP server go through FastAPI — no direct DB access from either, so there's one writer with WAL letting readers proceed.

---

## 2. Realtime transport choice — SSE

Picked over WebSocket for these reasons:

1. **All channels are server→client.** Mutations are REST. No bidirectional need.
2. **Browser-native reconnect + `Last-Event-Id` resume** are exactly what we need for an admin phone that suspends and resumes on Tailscale. WebSocket forces us to write that ourselves.
3. **HTTP/2 multiplexing under Caddy** removes the old SSE connection-limit complaint.
4. **`sse-starlette` is ~20 lines of server code.** Equivalent WebSocket scaffolding (heartbeat, reconnect, replay) is at least 2× the code.
5. **The MCP server can subscribe over plain HTTP** with an `httpx` streaming client — no browser API constraints.

Tradeoffs accepted: SSE is text-only (fine, all our payloads are JSON), and `EventSource` can't set custom headers (fine — same-origin cookies authenticate the admin, and the MCP server uses an HTTP client that *can* set headers).

### Channel design

Single endpoint: `GET /api/v1/events?topics=<csv>&last_event_id=...` (admin), plus `GET /api/v1/internal/events?topics=...` (MCP server, service-token auth).

Wire envelope:

```
id: 12345
event: module_update
data: {"topic":"page:pg_01HZX...","ts":"2026-05-25T14:00:00Z","payload":{...}}
```

Topics:

- `page:<page_id>` — module add/update/remove/reorder on that page (the common subscription).
- `module:<module_id>` — fine-grained, used by detail views and by the MCP server.
- `approvals` — pending-queue add/decide/expire. Always-on for the browser; subscribed by the MCP server's internal feed.
- `activity` — audit-row inserts. Subscribed by `/activity` when open.
- `log_stream:<module_id>` — high-frequency append deltas. Only subscribed when a log_stream module is visible.

Server-side ring buffer per topic: 5 minutes / 1000 events (`log_stream:*` topics get a smaller buffer; `approvals` gets a larger one — see open questions). On `Last-Event-Id` miss, server emits `kind: resync_required` and the client refetches via REST.

Heartbeats: `: keep-alive\n\n` every 15 seconds.

### Approval-decision delivery for the MCP server

Two-part: **MCP server holds an internal SSE subscription** to `approvals` so its in-memory pending cache stays fresh; **agents poll** `list_my_pending_requests` (MCP tool) in v1 because most agent runtimes don't yet support clean server-initiated push mid-tool-call. A future `subscribe_approvals` MCP tool can replace polling when the protocol/clients catch up.

---

## 3. Data model (SQLite)

### Tables (concise spec)

#### `agents`

| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | `agt_<ulid>` |
| display_name | TEXT NOT NULL UNIQUE | |
| description | TEXT | |
| api_key_hash | TEXT NOT NULL UNIQUE | argon2id encoded string (salt + params embedded) |
| permissions | TEXT NOT NULL `CHECK(json_valid)` | JSON: allowed module types, allowed page IDs, scopes |
| status | TEXT NOT NULL | `active` / `disabled` / `revoked` |
| created_at | TEXT NOT NULL | ISO 8601 UTC |
| last_active_at | TEXT | |
| last_key_rotated_at | TEXT | |

#### `pages`

| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | `pg_<ulid>` |
| slug | TEXT NOT NULL UNIQUE | URL-safe |
| name | TEXT NOT NULL | |
| description | TEXT | |
| kind | TEXT NOT NULL | `home` / `agent` / `custom` / `system` |
| owner_kind | TEXT | `user` or `agent` (nullable for system/home) |
| owner_id | TEXT | FK to `agents.id` when owner_kind=agent |
| deleted_at | TEXT | soft delete |
| created_at | TEXT NOT NULL | |

The `approvals` and `activity` views are virtual — rendered by querying directly, not seeded as page rows. `home` is seeded as a real row.

#### `modules`

| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | `mod_<ulid>` |
| type | TEXT NOT NULL | one of nine v1 types |
| title | TEXT | |
| owner_kind | TEXT NOT NULL | `user` or `agent` |
| owner_id | TEXT NOT NULL | |
| page_id | TEXT NOT NULL | FK `pages.id` ON DELETE CASCADE |
| position | INTEGER NOT NULL DEFAULT 0 | sort order |
| grid | TEXT `CHECK(grid IS NULL OR json_valid)` | optional `{x,y,w,h}` |
| permissions | TEXT NOT NULL `CHECK(json_valid)` DEFAULT `'{}'` | `{read, write}` |
| data | TEXT NOT NULL `CHECK(json_valid)` DEFAULT `'{}'` | type-specific |
| config | TEXT NOT NULL `CHECK(json_valid)` DEFAULT `'{}'` | type-specific |
| schema_version | INTEGER NOT NULL DEFAULT 1 | |
| version | INTEGER NOT NULL DEFAULT 1 | bumped on every write for optimistic concurrency |
| created_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | maintained on write |
| last_updated_by | TEXT NOT NULL | `user:admin` or `agent:<id>` |
| deleted_at | TEXT | soft delete |

#### `approval_requests`

| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | `apr_<ulid>` |
| agent_id | TEXT NOT NULL | FK `agents.id` ON DELETE RESTRICT |
| action_type | TEXT NOT NULL | `create_module`, `update_module_data`, `update_module_config`, `update_module_meta`, `delete_module`, `create_page`, `delete_page`, `fire_action_button` |
| target_kind | TEXT | `module` / `page` / `action_target` |
| target_id | TEXT | |
| proposed_payload | TEXT NOT NULL `CHECK(json_valid)` | |
| idempotency_key | TEXT | unique per `(agent_id, idempotency_key)` when present |
| status | TEXT NOT NULL DEFAULT 'pending' | `pending` / `approved` / `denied` / `applied` / `application_failed` / `superseded` / `expired` |
| created_at | TEXT NOT NULL | |
| decided_at | TEXT | |
| decided_by | TEXT | actor string OR `rule:<id>` OR `system:<reason>` |
| decision_reason | TEXT | |
| applied_at | TEXT | |
| executed_at | TEXT | action_button only |
| execution_result | TEXT `CHECK(json_valid)` | action_button only |
| expires_at | TEXT | TTL (default created_at + 7d) |

#### `approval_rules`

| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | `rule_<ulid>` |
| agent_id | TEXT NOT NULL | `*` for any agent |
| action_type | TEXT NOT NULL | concrete value, never `*` |
| module_type | TEXT | `*` / concrete / NULL when N/A |
| module_id | TEXT | |
| page_id | TEXT | |
| owner_scope | TEXT NOT NULL DEFAULT 'any' | `any` / `self` / `other` |
| outcome | TEXT NOT NULL | `auto_approve` / `deny` / `prompt` |
| priority | INTEGER NOT NULL DEFAULT 100 | lower wins |
| is_builtin | INTEGER NOT NULL DEFAULT 0 | seeded defaults; admins can disable but not delete |
| enabled | INTEGER NOT NULL DEFAULT 1 | |
| notes | TEXT | |
| created_at | TEXT NOT NULL | |
| created_by | TEXT NOT NULL | |
| last_applied_at | TEXT | |
| application_count | INTEGER NOT NULL DEFAULT 0 | |

#### `activity_log`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | high-volume append-only |
| timestamp | TEXT NOT NULL | ISO 8601 |
| actor_kind | TEXT NOT NULL | `user` / `agent` / `system` / `rule` |
| actor_id | TEXT | |
| action_type | TEXT NOT NULL | |
| target_kind | TEXT | |
| target_id | TEXT | |
| payload_summary | TEXT `CHECK(payload_summary IS NULL OR json_valid)` | ≤2KB; large payloads spill to `audit_blobs` |
| outcome | TEXT NOT NULL | `applied` / `queued` / `auto_approved` / `denied` / `error` |
| request_id | TEXT | FK `approval_requests.id` ON DELETE SET NULL |
| rule_id | TEXT | rule that decided this, if any |
| error_detail | TEXT | |

#### `iframe_allowlist`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| host_pattern | TEXT NOT NULL UNIQUE | exact host or `*.suffix` |
| description | TEXT | |
| added_at | TEXT NOT NULL | |

#### `action_targets`

| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | `act_<ulid>` |
| name | TEXT NOT NULL UNIQUE | |
| kind | TEXT NOT NULL | `webhook` / `local_script` / `mcp_tool` / `agent_message` |
| config | TEXT NOT NULL `CHECK(json_valid)` | per-kind schema; secrets stored here |
| enabled | INTEGER NOT NULL DEFAULT 1 | |
| created_at | TEXT NOT NULL | |
| deleted_at | TEXT | soft delete |

#### `agent_messages` (optional v1 feature for "send a message to agent X")

| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | `msg_<ulid>` |
| from_actor | TEXT NOT NULL | |
| to_agent_id | TEXT NOT NULL | FK `agents.id` ON DELETE CASCADE |
| payload | TEXT NOT NULL `CHECK(json_valid)` | |
| created_at | TEXT NOT NULL | |
| delivered_at | TEXT | |
| read_at | TEXT | |

#### `audit_blobs`

| Column | Type | Notes |
|---|---|---|
| sha256 | TEXT PK | content hash |
| body | TEXT NOT NULL | the full payload |
| created_at | TEXT NOT NULL | |

#### `request_idempotency`

| Column | Type | Notes |
|---|---|---|
| key | TEXT | client-supplied idempotency key |
| agent_id | TEXT NOT NULL | scope |
| tool | TEXT NOT NULL | scope |
| request_id | TEXT NOT NULL | FK `approval_requests.id` |
| response_snapshot | TEXT NOT NULL `CHECK(json_valid)` | |
| created_at | TEXT NOT NULL | |
| PRIMARY KEY (agent_id, tool, key) | | |

#### `schema_migrations`

| Column | Type | Notes |
|---|---|---|
| version | TEXT PK | e.g. `20260525_0001_init` |
| applied_at | TEXT NOT NULL | |
| checksum | TEXT | sha256 of migration file |

**No `sessions` table** — admin auth uses a signed cookie (HMAC + secret in env or one-row `kv_settings`). Rotate secret to invalidate all sessions.

### Indexes

| Index | Table | Columns |
|---|---|---|
| `idx_modules_page_position` | modules | (page_id, position) WHERE deleted_at IS NULL |
| `idx_modules_owner` | modules | (owner_kind, owner_id) WHERE deleted_at IS NULL |
| `idx_modules_type` | modules | (type) WHERE deleted_at IS NULL |
| `idx_approvals_status_created` | approval_requests | (status, created_at DESC) |
| `idx_approvals_agent_created` | approval_requests | (agent_id, created_at DESC) |
| `idx_approvals_target` | approval_requests | (target_kind, target_id) |
| `idx_rules_lookup` | approval_rules | (action_type, agent_id, module_type, module_id, page_id) WHERE enabled=1 |
| `idx_activity_ts` | activity_log | (timestamp DESC) |
| `idx_activity_actor_ts` | activity_log | (actor_kind, actor_id, timestamp DESC) |
| `idx_activity_target` | activity_log | (target_kind, target_id, timestamp DESC) |
| `idx_activity_request` | activity_log | (request_id) |
| `idx_agent_messages_inbox` | agent_messages | (to_agent_id, delivered_at) |

UNIQUE constraints on `agents.api_key_hash`, `pages.slug`, `iframe_allowlist.host_pattern`, `action_targets.name` already give the auth/lookup indexes.

### JSON storage approach

- TEXT columns with `CHECK(json_valid(...))`.
- Filterable scalars (type, status, position) are promoted to scalar columns; everything else stays inside `data`/`config`/`payload_summary`.
- For any future hot filter on an inner field, add an expression index on `json_extract(...)`.
- Pydantic (FastAPI) validates the JSON shape against module-type schemas; SQLite only guarantees parseability.

### ID strategy

ULID with type prefix, stored as TEXT (`mod_`, `pg_`, `agt_`, `apr_`, `rule_`, `act_`, `msg_`). Lexicographic time order, copyable in logs, type-disambiguated. `activity_log.id` and `iframe_allowlist.id` use INTEGER for compactness because they're never externally referenced.

### Soft vs hard delete

- Soft: `modules`, `pages`, `action_targets` (referenced by audit/history).
- Hard: `approval_requests` (status lifecycle terminates them), `agent_messages`, `iframe_allowlist`.
- Never delete `agents` — set `status='revoked'`.

### Schema versioning of module payloads

- `modules.schema_version` per row.
- Code-side migration registry keyed by `(module_type, from_version, to_version)`.
- Lazy migration on read; eager migration via admin-triggered batch job.

### SQLite pragmas

| Pragma | Value |
|---|---|
| `journal_mode` | `WAL` |
| `synchronous` | `NORMAL` |
| `foreign_keys` | `ON` (per connection) |
| `busy_timeout` | `5000` |
| `temp_store` | `MEMORY` |
| `mmap_size` | `268435456` (256 MB) |
| `cache_size` | `-20000` (~20 MB) |

Nightly `PRAGMA wal_checkpoint(TRUNCATE)` + `PRAGMA optimize`.

### Migrations

**Alembic.** Use batch mode for table alterations (SQLite ALTER TABLE limitations). Forward-only in prod; downgrade for dev convenience. Pin SQLite ≥ 3.35.

### Concurrency

Single-writer reality of SQLite. Both Next.js and MCP go through FastAPI, so one process owns the writer lock. Use `BEGIN IMMEDIATE` for write transactions to acquire the lock upfront and avoid deferred-upgrade races. Approval engine + write are wrapped in one transaction per request.

---

## 4. v1 module type catalog (JSON schemas)

### Cross-cutting conventions

- **`severity` enum:** `info | success | warning | error | muted`. Tailwind class map lives client-side.
- **`icon`:** Lucide names in kebab-case (`pattern: ^[a-z][a-z0-9-]{0,40}$`). Unknown names fall back to a dot icon.
- **Timestamps:** RFC 3339 strings (`format: date-time`).
- **Module envelope** (assumed wrapper around every `data`/`config` below): `{id, type, title, owner_kind, owner_id, config, data, version, updated_at, ...}`.
- **iframe allowlist** is server-side config; agents reference `src` values whose host must match. Rejections return `iframe_host_not_allowed` and are non-retryable.
- **`action_button`** stores only `action_target_id`. The webhook URL / script / MCP tool args live in the `action_targets` table, not in the module.

### 4.1 `markdown`

```json
{
  "data": {
    "type": "object", "required": ["body"], "additionalProperties": false,
    "properties": {
      "body": { "type": "string", "maxLength": 50000 },
      "rendered_at": { "type": "string", "format": "date-time" }
    }
  },
  "config": {
    "type": "object", "additionalProperties": false,
    "properties": {
      "collapsed_by_default": { "type": "boolean", "default": false },
      "max_height_px": { "type": "integer", "minimum": 80, "maximum": 2000, "default": 600 },
      "callout_severity": { "$ref": "#/definitions/severity" },
      "show_rendered_at": { "type": "boolean", "default": true }
    }
  }
}
```

Rendered with `react-markdown` + `rehype-sanitize` (no `rehype-raw`). Code highlighting via server-rendered Shiki. Approval default: `auto_approve` for owning agent.

### 4.2 `key_value`

```json
{
  "data": {
    "type": "object", "required": ["fields"], "additionalProperties": false,
    "properties": {
      "fields": {
        "type": "array", "maxItems": 40,
        "items": {
          "type": "object", "required": ["key","value"], "additionalProperties": false,
          "properties": {
            "key": { "type": "string", "maxLength": 80 },
            "value": { "type": ["string","number","boolean","null"], "maxLength": 300 },
            "severity": { "$ref": "#/definitions/severity" },
            "icon": { "$ref": "#/definitions/icon" },
            "unit": { "type": "string", "maxLength": 16 },
            "hint": { "type": "string", "maxLength": 200 }
          }
        }
      },
      "updated_at": { "type": "string", "format": "date-time" }
    }
  },
  "config": {
    "type": "object", "additionalProperties": false,
    "properties": {
      "layout": { "enum": ["stacked","two-column","inline-chips"], "default": "two-column" },
      "show_icons": { "type": "boolean", "default": true },
      "value_format": { "enum": ["auto","monospace","humanize-number","humanize-bytes"], "default": "auto" },
      "show_updated_at": { "type": "boolean", "default": true }
    }
  }
}
```

Common high-frequency module (status snapshots). Approval default: `auto_approve` for owning agent.

### 4.3 `table`

`data.columns`: array (max 12) of `{id, label, type∈[text|number|timestamp|severity|icon|link|action], align, hide_on_mobile}`. `data.rows`: array (max 500) of `{row_id?, severity?, cells: {<col_id>: scalar | {text, href?, icon?, severity?, action_target_id?, confirm?}}}`. `data.updated_at`.

`config`: `empty_message`, `row_density∈[compact|normal|comfortable]`, `mobile_layout∈[scroll|card-stack]`, `default_sort`.

Mobile collapses to card stack. Link cells get `rel="noopener noreferrer"`; only `http/https/mailto` schemes allowed. Approval default: `auto_approve` row updates, `prompt` on column changes.

### 4.4 `timeseries`

`data.series`: array (max 6) of `{id, label, color_token, points: [{t, v}]}`. Max 2000 points/series. `data.window_start`, `data.window_end`.

`config`: `chart_type∈[line|bar|area]`, `y_axis: {label, min, max, unit, format∈[auto|percent|bytes|duration_ms]}`, `x_axis`, `show_legend`, `height_px`.

Recharts in v1; uPlot is the fallback if perf becomes an issue. Approval default: `auto_approve` for owning agent.

### 4.5 `log_stream`

`data.entries`: array (max 1000) of `{t, message, severity?, source?, icon?}`. `data.last_appended_at`.

`config`: `ring_buffer_size` (20–1000, default 200), `order∈[newest-first|oldest-first]`, `default_filter_severity`, `show_source`, `monospace`.

Append-only fast path via MCP `append_log` tool. Messages are HTML-escaped (no markdown). Approval default: `auto_approve` appends from owner; `prompt` on full replacement (clear).

### 4.6 `link_list`

`data.links`: array (max 50) of `{label, href, description?, icon?, severity?, external?}`. `data.updated_at`.

`config`: `layout∈[list|grid|chips]`, `show_descriptions`, `show_icons`, `open_in_new_tab`.

Only `http/https/mailto` hrefs accepted. Approval default: `auto_approve` for owning agent.

### 4.7 `iframe`

`data`: `{src, title?}`. `config`: `height_px`, `mobile_height_px`, `sandbox` (array allowing `allow-scripts|allow-same-origin|allow-forms|allow-popups`; `allow-same-origin` requires per-host opt-in stored server-side), `referrer_policy`, `show_chrome`.

`src` validated against `iframe_allowlist` on every update. Approval default: **`prompt` for any `data.src` change** — highest-risk module. `auto_approve` for config tightening; `prompt` for loosening.

### 4.8 `action_button`

`data`: `{label, action_target_id, icon?, severity?, disabled?, last_result?}`. `last_result` is server-written, agent-readable.

`config`: `confirm` (default true), `confirm_text`, `cooldown_seconds`, `style∈[primary|secondary|destructive]`, `show_last_result`.

Action targets resolved server-side; secrets never appear in the module payload. Approval default: `prompt` on `action_target_id` change or `confirm: true→false`; `auto_approve` on label/icon/disabled by owner.

### 4.9 `notification`

`data`: `{message, severity, created_at, expires_at?, dismissed_at?, action?: {label, href?|action_target_id?}, icon?}`.

`config`: `dismissible`, `auto_dismiss_seconds`, `pin_to_top`, `sound`.

Sorted by severity then created_at. Per-agent rate limit: 30 new notifications/hour. Cap of 50 active notifications system-wide; oldest dropped beyond that. Approval default: `auto_approve` for owner (within rate limit).

---

## 5. HTTP API surface

Two consumers — admin browser and the MCP server. Two URL prefixes under one version: `/api/v1/...` (admin) and `/api/v1/internal/...` (MCP). Health checks at `/healthz` and `/readyz`.

### Cross-cutting

- **Versioning:** `/api/v1/` from day one.
- **Errors:** RFC 7807 `application/problem+json` with stable `code` field (`module.not_found`, `approval.pending_exists`, `idempotency.mismatch`, …).
- **Idempotency:** `Idempotency-Key` header on POSTs. Required on the internal surface; optional but recommended on the admin surface.
- **CORS/CSRF:** Same-origin; HTTP-only `session` cookie + non-HttpOnly `csrf_token`; `X-CSRF-Token` required on state-changing browser requests. MCP service auth bypasses CSRF.
- **Optimistic concurrency:** Weak ETag on modules/pages/agents/action_targets. Admin uses `If-Match` header; internal surface uses `expected_etag` in body (because agents read, think, then write later).
- **OpenAPI** auto-generated by FastAPI; Swagger UI behind session auth at `/api/v1/docs`.

### `/auth`

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/v1/auth/login` | `{password}` | `200 {user}` + cookies; `401 auth.invalid_credentials`; progressive delay after failures |
| POST | `/api/v1/auth/logout` | — | `204` clears cookies |
| GET | `/api/v1/auth/me` | — | `200 {user}` |

(Single admin: no username, just password. Recovery is filesystem-level.)

### `/modules`

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/modules` | filters: `page_id`, `type`, `cursor`, `limit≤200` |
| GET | `/api/v1/modules/{id}` | returns `Module` + `ETag` |
| POST | `/api/v1/modules` | bypasses approval; `Idempotency-Key` |
| PATCH | `/api/v1/modules/{id}` | `If-Match`; merge-patch on `data`/`config` |
| DELETE | `/api/v1/modules/{id}` | soft delete, 30-day retention |
| POST | `/api/v1/modules/reorder` | atomic page reorder |
| POST | `/api/v1/modules/bulk` | up to 100 ops |

### `/pages`

CRUD + `POST /api/v1/pages/reorder`. Slug pattern `^[a-z0-9-]{1,40}$`. Delete with `?cascade=true|false`.

### `/agents`

CRUD + `POST /api/v1/agents/{id}/rotate-key` (returns plaintext once) + `POST /api/v1/agents/{id}/enable|disable`. `scopes` is an allow-list of action types (empty = all).

### `/approval-requests`

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/approval-requests` | filters: status, agent_id, action_type, page_id, dates |
| GET | `/api/v1/approval-requests/{id}` | includes diff preview |
| POST | `/api/v1/approval-requests/{id}/approve` | body: `{reason?, create_rule?}` |
| POST | `/api/v1/approval-requests/{id}/deny` | body: `{reason?, create_rule?}` |
| POST | `/api/v1/approval-requests/bulk-decide` | up to 50 |

### `/approval-rules`

CRUD + `POST /{id}/preview` (dry-run against history) + `POST /{id}/revoke` (`{reverse_decisions?}`).

### `/activity-log`

Read-only. List/get/search. `kind`, `actor`, `target_kind`, `target_id`, `q`, `after`, `before`, cursor. FTS5 for `q`.

### `/iframe-allowlist`, `/action-targets`, `/module-schemas`

Standard CRUD on the first two (delete-with-references guard, secrets redacted in responses for action_targets). Module-schemas is read-only and shared by frontend + MCP `get_module_schema`.

### `/events` (SSE)

`GET /api/v1/events?topics=<csv>&last_event_id=...` — admin session.

### `/internal/*` (MCP server only)

Auth: `Authorization: Bearer <service_secret>` + `X-Agent-Id: <agent_id>`. The MCP server validates the agent's API key before calling internal endpoints.

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/internal/propose-module` | routes through approval engine; returns `{status: applied|pending|denied, request_id, …}` |
| POST | `/api/v1/internal/update-module` | same triad; `expected_etag` honored before enqueue |
| POST | `/api/v1/internal/delete-module` | same triad |
| POST | `/api/v1/internal/propose-page` | same triad |
| POST | `/api/v1/internal/append-log` | always `applied` if rule matches (default builtin); `Idempotency-Key` |
| POST | `/api/v1/internal/fire-action` | same triad + execution result on applied |
| GET | `/api/v1/internal/my-modules` | scoped to `X-Agent-Id` |
| GET | `/api/v1/internal/my-pending-requests` | |
| GET | `/api/v1/internal/module-schema/{type}` | alias of public schema endpoint |
| GET | `/api/v1/internal/whoami` | sanity check |
| GET | `/api/v1/internal/events` | SSE — `approvals` topic for MCP cache |

Idempotency-Key is **required** on POSTs here. Errors use `problem+json` with `request_id` cross-referencing `activity_log`.

---

## 6. MCP tool surface

### Preamble

- **Transport: HTTP-streamable** (the MCP "Streamable HTTP" binding). A single URL like `https://homebase.<tailnet>.ts.net/mcp` reachable from any agent (local, cloud, or VS Code-launched). A thin stdio→HTTP shim ships for local-only agents that strictly require stdio.
- **Auth:** Per-agent API key (`hb_agt_<base32>`, 32 bytes, argon2id at rest) in `Authorization: Bearer …`. MCP `initialize` records client self-report but trusts only the key. MCP server caches `agent_id` for the session; revocation invalidates within ≤30s.
- **Internal API contract:** Every tool maps to one or two `/api/v1/internal/...` calls. The MCP server stores no state and runs no business logic.
- **Tool-description budget:** ≤400 tokens each. Verbose docs live in `get_module_schema` (read on demand).
- **Rate limiting:** Token bucket per agent (default 60 writes/min, 600 reads/min). `429` with `retry_after_ms`. Agents must honor it; do not retry `pending` results.
- **NOT in v1:** cross-agent mutation, admin tools, raw SQL, bulk imports, file uploads, push of approval decisions to agents (polling only).

### Tools

#### Write

1. **`propose_module(page_id, type, title, data, config, permissions?, idempotency_key?)`**
   - Returns `{status, module_id, request_id?, reason?, applied_at?, module?}`.
   - Description tells agents: call `get_module_schema` first; never re-call to overwrite (use `update_module`); never retry a `pending`.

2. **`update_module(module_id, data?, config?, title?, position?, expected_version?, idempotency_key?)`**
   - Replace-wholesale semantics on `data`/`config`; pass `null` to clear an optional field.
   - `expected_version` triggers `Conflict` on mismatch.
   - Routine `data`-only updates by owner are typically `applied`.

3. **`delete_module(module_id, expected_version?, idempotency_key?, reason?)`**
   - Almost always `pending`. Soft-deleted for 7 days server-side; the agent sees it as gone on `applied`.

4. **`propose_page(name, slug?, description?, idempotency_key?)`**
   - High-friction; usually `pending`.

5. **`fire_action(module_id, payload?, idempotency_key?)`**
   - Target must be an `action_button` module. Response includes `mode∈[sync|async]`, `result` or `job_id`. Approval gates whether it fires; execution success/failure is reported in `result` (or via future `get_job`).

6. **`append_log(module_id, entry, idempotency_key?)`**
   - Fast path for `log_stream`. Always `applied` if the default builtin rule is in place. Returns `buffer_size` and optional `truncated_count`.

#### Read

7. **`list_my_modules(page_id?, type?, limit?, cursor?)`** — only modules the calling agent owns. Each item includes `staleness∈[fresh|stale|unknown]`.

8. **`get_module(module_id)`** — full state + `staleness`. Used for `expected_version` round-trips and for inspecting `action_button` payload schemas before `fire_action`.

9. **`list_pages(limit?, cursor?)`** — pages the agent has read access to, with `access∈[read|write]`.

10. **`list_my_pending_requests(status_filter?, limit?, cursor?)`** — reconciliation for `pending` responses. Includes recently-resolved (last 24h).

11. **`get_module_schema(type)`** — JSON Schema for `data` + `config`, plus 1–3 examples and `permissions_default`. Session-lifetime cache OK on the agent side.

Each tool's MCP description includes:
- One-line purpose.
- When to use / when not to.
- Status semantics and what to do per status.
- Idempotency guidance.
- Honor `retry_after_ms`; do not retry `pending`.

All write tools return either an MCP error (auth, validation, not-found, rate-limit, service unavailable) or a payload-level status (`applied | pending | denied`). Payload-level `denied` is **not** an MCP error — the call was structurally valid; only the policy refused.

---

## 7. Approval engine

The trust boundary. Goals in priority order: **safety, low friction, auditability, cheap hot-path**.

### 7.1 Matching algorithm

**Wildcards: explicit `*`**, not NULL. NULL means "this dimension does not apply to this action type" (e.g. a `delete_page` rule's `module_id` is NULL by definition, not `*`).

**`action_type` is never wildcard.** Forces explicit per-action authorization.

**Specificity score** (most specific to least, additive bits):

1. `module_id` matches exactly
2. `page_id` matches exactly
3. `module_type` matches exactly
4. `agent_id` matches exactly
5. `owner_scope ∈ {self, other}` (vs `any`)

**Tiebreakers in order:** lower `priority` wins → newer `created_at` wins → at equal specificity *and* priority, `deny` beats `auto_approve` (safe default for ambiguous configs).

**Important:** `deny` does **not** auto-beat `auto_approve` at *different* specificities. A more-specific `auto_approve` wins over a broader `deny`. The rule editor surfaces a warning when a new rule shadows or is shadowed by another.

**Cost:** in-memory cache `dict[action_type] → list[rule]` sorted by specificity desc, invalidated by a `rules_version` int bumped on rule CRUD. Per-request matching is a linear scan over `O(rules for action_type)` — in practice tens of entries, sub-microsecond.

**Pseudocode:**

```
match_rule(request):
  for rule in cache.rules_by_action[request.action_type]:  # sorted by specificity desc
    if rule.agent_id != "*" and rule.agent_id != request.agent_id: continue
    if rule.module_type not in (None, "*") and rule.module_type != request.module_type: continue
    if rule.module_id  not in (None, "*") and rule.module_id  != request.module_id:  continue
    if rule.page_id    not in (None, "*") and rule.page_id    != request.page_id:    continue
    if rule.owner_scope == "self"  and not request.agent_owns_target: continue
    if rule.owner_scope == "other" and     request.agent_owns_target: continue
    return rule
  return None  # → default policy: prompt
```

### 7.2 Default (built-in) rule set

Seeded on first run with `priority=200` and `is_builtin=true` (admins can disable but not delete):

| agent | action | scope | outcome |
|---|---|---|---|
| `*` | `update_module_data` | `owner_scope=self` | `auto_approve` |
| `*` | `update_module_data` | `owner_scope=other` | `prompt` |
| `*` | `update_module_config` | any | `prompt` |
| `*` | `update_module_meta` | any | `prompt` |
| `*` | `create_module` | any | `prompt` |
| `*` | `delete_module` | any | `prompt` |
| `*` | `create_page` | any | `prompt` |
| `*` | `delete_page` | any | `prompt` |
| `*` | `fire_action_button` | any | `prompt` |
| `*` | `append_log` (`update_module_data` flavor for `log_stream`) | `owner_scope=self` | `auto_approve` |

Ownership-aware matching is a first-class rule column (`owner_scope`), not a pseudo-rule.

### 7.3 Default when no rule matches

**`prompt`.** Anything we forgot to ship a rule for fails safe to admin review.

### 7.4 Edge cases

- **Rule added while a request is pending.** Rule-creation dialog shows the count of matching pending requests with an opt-in checkbox **(default off)** to apply retroactively. If checked, atomic with the rule insert; audit logs annotate as `decided_by = "rule:<id> (retroactive)"`.
- **Rule revoked mid-flight.** Already-in-flight applies proceed; audit row records `rule_revoked_after_decision`.
- **Agent disabled mid-request.** Pending requests for that agent transition to `denied` with reason `agent_disabled`; approved-but-not-applied transition to `denied` with reason `agent_disabled_post_approval`. The agent can resubmit when re-enabled.
- **Concurrent updates from two writers.** Last-write-wins with `version` bump; both attempts logged. Optimistic concurrency available via `expected_version` for callers that want it.
- **Module deleted while update pending.** Pending requests targeting the deleted module flip to `superseded` in the delete's transaction.
- **Approval queue overflow.** Soft cap 200/agent, hard cap 1000 total — beyond which MCP writes return `queue_full`. v1.5: pattern-detection banner ("47 identical requests, auto-approve all and create rule?").
- **Replay / duplicate.** `request_idempotency` table keyed by `(agent_id, tool, key)`. Same-agent collisions return the original outcome. 30-day TTL.
- **Self-referential delete.** Default `prompt`; admin can flip the built-in rule slot for `delete_*` with `owner_scope=self` to `auto_approve` if desired.
- **Bulk approve.** Per-row validation (target still exists? agent still enabled? payload still valid?). Per-row atomicity with a summary report — not all-or-nothing.
- **"Create rule from approval"** defaults to narrowest meaningful scope: target has `module_id` → `(agent_id, action_type, module_id)`; only `page_id` → `(agent_id, action_type, page_id)`; create_module → `(agent_id, action_type, module_type)`. Admin can widen before saving. Never auto-broadens `agent_id` to `*`.
- **Rule shadowing.** Specificity wins regardless of `deny`/`auto_approve`. UI marks rules as "currently shadowed by rule #N".
- **Action button: approved vs executed.** Distinct fields (`approved_at`, `applied_at`, `executed_at`, `execution_result`). A webhook 500 is `approved + executed + failed`.

### 7.5 Lifecycle

```
created → pending → ┌─ approved → applied
                    │             └─ application_failed
                    ├─ denied
                    ├─ superseded
                    └─ expired
```

`pending` TTL default **7 days** (configurable). `approved` doesn't expire — applies within milliseconds.

`fire_action_button` adds sub-states `executed | execution_failed` under `applied`.

### 7.6 Audit

Every transition writes `activity_log` with `from_status`, `to_status`, `decided_by` (`admin:<user>` / `rule:<id>` / `system:<reason>`), `rule_id`, `payload_snapshot` (or `audit_blobs` hash for >32KB), and timestamp. The rule detail page lets the admin see every decision a given rule has made.

Retention: append-forever in v1. Audit log is read-only from the UI.

### 7.7 UI requirements

- **Approvals queue:** per-row Approve once / Approve + rule / Deny / Deny + rule; multi-select bulk; agent + action filters; diff preview on updates.
- **Rules page:** flat table with shadow indicators; inline enable/disable/edit; "matched N times in last 30 days."
- **Activity:** filter by rule; "show everything this rule has ever approved."
- **Mobile:** pending queue + swipe-approve/deny is the minimum surface; rule editor is desktop-first / mobile-read-only.

---

## 8. Frontend

### 8.1 Information architecture

- **Desktop:** collapsible sidebar (Home, Agents [expandable], Approvals, Activity, Settings, + Pages group).
- **Mobile:** bottom tab bar with four items — Home / Approvals (badge) / Activity / Settings. Agents and Pages in a hamburger drawer.
- **Pending badge** lives on the Approvals nav item; hydrated server-side, updated via SSE.
- **Command palette** (`⌘K` / `Ctrl+K`) using `cmdk`: pages, agents, settings sub-pages, "edit current page," "add module."

### 8.2 Pages

| Page | Route | SC/CC split | Subscribes to |
|---|---|---|---|
| Home | `/` | SC fetches; CC `<PageView>` for interactivity | `page:home`, `notifications:admin`, `approvals` (badge) |
| Agent | `/agents/[id]` | SC fetches agent+modules+activity; CC for permissions panel | `agent:{id}` |
| Approvals | `/approvals` | SC initial queue; CC owns mutations + filters | `approvals` |
| Activity | `/activity` | SC initial page; CC for search + new-rows pill | `activity` |
| Settings | `/settings/*` | SC layout; per-sub-route mixes | none |
| Page editor | `/?edit=1` (mode) | CC `<EditablePageGrid>` swapped in | current page topic |

Mobile considerations baked in per-page (covered below).

### 8.3 Component library

- **`<ModuleHost>`** — wraps any module with title, owner badge, edit/delete controls in edit mode, pulse-on-update animation.
- **`<ModuleRenderer>`** — switch on `type`; validates `data`/`config` against schema and falls back to an error tile on invalid payloads.
- **Per-type renderers** for the nine v1 types — `<MarkdownModule>`, `<KeyValueModule>`, `<TableModule>`, `<TimeseriesModule>` (Recharts), `<LogStreamModule>` (virtualized + SSE-driven), `<LinkListModule>`, `<IframeModule>` (sandbox + allowlist check), `<ActionButtonModule>`, `<NotificationModule>`.
- **`<SchemaForm>`** — `@rjsf/core` with a Tailwind/shadcn-style theme. Custom widgets: markdown editor (`@uiw/react-md-editor`), severity picker, icon picker (Lucide grid), key-value list, table column editor.
- **`<ApprovalCard>`** — Approve / Deny / Auto-approve-like-this. Optimistic with 5s undo toast.
- **`<RuleEditor>`** — used in `/settings/rules` and the approve+rule flow. Pre-fills from a request when launched there.
- **`<AgentBadge>`**, **`<ActivityRow>`**, **`<PageNav>`**, **`<PageGrid>`** (CSS Grid, 12-col desktop / 6-col tablet / 1-col mobile), **`<EditablePageGrid>`** (dnd-kit `<DndContext>` wrapper).
- Cross-cutting: `<CommandPalette>`, `<Toast>`, `<ConfirmDialog>`, `<Drawer>`, `<Sheet>` (mobile full-screen), `<RelativeTime>`, `<EmptyState>`, `<RealtimeProvider>`.

### 8.4 Realtime integration

`<RealtimeProvider>` mounted in `app/layout.tsx` opens **one** `EventSource` to `/api/v1/events?topics=...`. Channel routing into a Zustand store via `useChannel(channel, handler)`. Topic set changes on nav (close + reopen with new `topics` query string). `approvals` stays in the always-on set. Reconnect handled by `EventSource` defaults; `Last-Event-Id` resume on the server side. Activity events surface in the activity page as a "N new" sticky pill — never auto-prepended (disorienting in a log).

### 8.5 Edit mode

Toggled via header pencil or palette command, URL-synced (`?edit=1`). dnd-kit `<DndContext>` for reorder; minSize/maxSize per module type; custom resize wrapper (fall back to `react-grid-layout` if homegrown bloat). Add-module flow: type picker → `<SchemaForm>` → live preview pane (desktop) or "Preview" tab (mobile). All admin edits bypass approval; optimistic mutations with rollback. No version history in v1 — "Recently deleted" recovery list (30 days) instead.

### 8.6 Mobile

- Home stacks single-column ignoring `x`/`w`.
- Tall modules clamp to a `maxHeight` with internal scroll.
- Approvals: swipe right approves / swipe left denies, with 3s undo toast; buttons remain. Long-press enters multi-select.
- Edit mode: drag/resize disabled; per-module kebab menu (Edit / Move up / Move down / Delete); full-screen sheets for form editing.
- Bottom tab bar safe-area aware.

### 8.7 Auth UX

`/login` is server-rendered, password-only. HTTP-only session cookie, 30-day sliding. Logout in `/settings/account`. Progressive delay on failed attempts (3 → 5s, 6 → 30s, 10 → 5min) instead of hard lockout — single-admin self-DoS is the bigger risk.

---

## 9. Phase-by-phase roadmap

Each phase is sized for ~1–2 weeks of focused work. **Tasks marked `[‖]` are good parallel-subagent candidates** at implementation time.

### Phase 1 — Backend skeleton + data model

**Deliverables:**

- FastAPI app scaffolding, settings, structured logging, `/healthz` + `/readyz`.
- Alembic init + initial migration creating all tables + indexes.
- Pydantic models for all entities.
- Admin auth: login/logout/me; password hash in `kv_settings`; signed cookie; CSRF middleware.
- Module CRUD endpoints (admin path only — no internal surface yet, no approval engine).
- Page CRUD.
- Agent CRUD + key rotation (keys not yet usable for anything — no MCP).
- Module schema registry: per-type Pydantic models + JSON Schema export endpoint.
- Pytest harness with an isolated test SQLite (in-memory + WAL emulation).

**Parallel subagent fan-out:**

- `[‖]` One subagent per resource group (modules, pages, agents) implementing models + endpoints in parallel.
- `[‖]` Separate subagent for the schema registry + the nine Pydantic module-data models.
- `[‖]` Separate subagent for auth + CSRF + signed cookie helpers.
- Main thread integrates and runs the test suite.

**Done when:** `curl` against `/api/v1/modules` and `/api/v1/pages` works end-to-end with a fresh DB and a signed-in admin.

### Phase 2 — Frontend basics

**Deliverables:**

- Next.js App Router scaffolding, Tailwind, shadcn primitives, login page.
- `<RealtimeProvider>` placeholder (no SSE yet — stub).
- Home page + page nav (desktop sidebar + mobile bottom bar).
- Module rendering for **markdown, key_value, table, link_list** (the four cheapest).
- `<ModuleHost>` + `<ModuleRenderer>` + `<PageGrid>` (view mode only).
- Page editor toggle + `<SchemaForm>` (rjsf) for create/edit of the four types.
- Settings shell with `/settings/agents` (register agent, view key once) and `/settings/pages`.

**Parallel subagent fan-out:**

- `[‖]` One subagent per module renderer.
- `[‖]` `<SchemaForm>` + rjsf theme + custom widgets (markdown editor, key-value list, table column editor) in parallel with renderers.
- `[‖]` Mobile bottom-nav + responsive layout primitives.
- Main thread wires layout, fetches, and edit-mode toggle.

**Done when:** an admin can create a home page, add markdown/key_value/table/link_list modules manually, reorder them (drag-drop on desktop), and view on phone.

### Phase 3 — MCP server + approval engine

**Deliverables:**

- Approval engine: rule cache, matching, default rule seed migration, lifecycle state machine, `request_idempotency`.
- `/api/v1/internal/*` endpoints for the four-type subset (propose_module, update_module, delete_module).
- `/api/v1/approval-requests/*` + `/api/v1/approval-rules/*` admin endpoints.
- `/approvals` page + `<ApprovalCard>` + `<RuleEditor>` + "approve + rule" flow.
- MCP server process: HTTP-streamable transport, auth, the 11 tools wired to internal endpoints, tool descriptions polished.
- Activity log writes on every decision; `/activity` page (read-only).

**Parallel subagent fan-out:**

- `[‖]` Approval engine (matching + lifecycle + idempotency) — one subagent.
- `[‖]` Internal endpoints — one subagent.
- `[‖]` MCP server + tool definitions — one subagent.
- `[‖]` `/approvals` frontend + `<RuleEditor>` — one subagent.
- `[‖]` Default rule seeding migration + agent registration UX — one subagent.
- Main thread integrates and runs an end-to-end test (register agent → MCP `propose_module` → request appears in queue → admin approves → module appears on page).

**Done when:** an agent using its API key can propose a markdown module via the MCP tool, the admin sees the request in `/approvals`, approves it (once or with a rule), and the module lands on the right page.

### Phase 4 — Remaining module types

**Deliverables:**

- `<TimeseriesModule>` (Recharts).
- `<LogStreamModule>` + `append_log` MCP tool + `log_stream:<id>` SSE channel.
- `<IframeModule>` + iframe allowlist UI in `/settings/iframe-allowlist` + server-side host validation.
- `<NotificationModule>` + home-page pinning + per-agent rate limit.
- `<ActionButtonModule>` + `action_targets` table + `/settings/action-targets` UI + `fire_action` MCP tool + target dispatcher (webhook + local_script first, mcp_tool + agent_message later).
- Schema-form widgets for these types (chart series editor, icon picker tuning, action target picker).

**Parallel subagent fan-out:**

- `[‖]` One subagent per remaining renderer (5 modules).
- `[‖]` Action target dispatcher (webhook + script kinds) in parallel.
- `[‖]` Iframe allowlist endpoint + UI.
- Main thread integrates and writes integration tests per module.

**Done when:** all nine types render, edit-form, and round-trip through both admin and agent paths.

### Phase 5 — Realtime

**Deliverables:**

- `sse-starlette` integration + `EventBus` singleton.
- `GET /api/v1/events` admin endpoint with ring buffer + `Last-Event-Id` resume.
- `GET /api/v1/internal/events` for MCP server.
- Publish hooks in every write path (modules, approvals, activity, log_stream).
- Wire `<RealtimeProvider>` to real SSE; replace stubs.
- Pending badge live updates; module pulse-on-update; approvals queue live; activity "N new" pill; `log_stream` tailing.
- MCP server's pending-decision cache subscribes to internal SSE.

**Parallel subagent fan-out:**

- `[‖]` Server `EventBus` + endpoint — one subagent.
- `[‖]` Client `<RealtimeProvider>` + Zustand wiring — one subagent.
- `[‖]` Per-page subscription rewiring (home, approvals, activity, log_stream) — one subagent.
- Main thread integration-tests reconnect/resume behavior across simulated drops.

**Done when:** approving a request on desktop instantly updates the queue, the badge, and the affected module on a phone open in another tab — no refresh needed.

### Phase 6 — Polish

**Deliverables:**

- Activity log search (FTS5) + filters.
- Approvals + activity export endpoints if needed (`/export`).
- Rule preview ("would have matched N historical requests").
- "Rule suggestion" banner on high queue volume.
- Mobile swipe approve/deny gestures + haptic-visual confirmation.
- Empty-state illustrations and copy pass.
- Command palette commands for power-user navigation.
- Dark mode polish + system-preference detection.
- Docker Compose + Caddyfile + deployment docs.
- Backup script (sqlite `.backup` + audit_blobs export).

**Parallel subagent fan-out:**

- `[‖]` FTS5 search + filters — one subagent.
- `[‖]` Mobile gesture handlers + responsiveness audit — one subagent.
- `[‖]` Docker Compose + Caddyfile + Tailscale deploy doc — one subagent.
- `[‖]` Empty states + copy pass — one subagent.
- Main thread runs a final end-to-end exercise on a phone.

**Done when:** the dashboard is the home page on the admin's phone for a week without filing a single bug against it.

---

## 10. Open questions and risks

Consolidated and de-duplicated from the seven design workstreams, prioritized as **must answer pre-implementation (P0)**, **should answer mid-build (P1)**, or **defer (P2)**.

### P0 — answer before starting Phase 1

> **P0 #1 resolution (Phase 3):** Revoked agents keep their modules readable;
> no mutation, no reassignment. Implemented via the active-status check on
> `/internal/*` and the soft-delete path on revoked agents.
>
> **P0 #2 resolution (Phase 1):** 32 KB threshold wired in
> `app/services/audit.write_event`; spills to `audit_blobs`.
>
> **P0 #3 resolution (Phase 1):** schema versioning is lazy on read, write-back
> on next mutation.
>
> **P0 #4 resolution (Phase 1):** `fire_action` mode stored on
> `action_targets.mode`.
>
> **P0 #5 resolution (Phase 1):** iframe allowlist supports host + optional
> `path_prefix` column.
>
> **P0 #7 resolution (Phase 3):** pending TTL is 7 days; expiration flips to
> distinct status `expired`, with a sweeper at
> `app/approval/expiry.expire_stale_pending`.
>
> **Provisional module IDs (Phase 3 addition):** When `propose-module` routes
> to `pending`, the backend mints a `mod_<ulid>` upfront, stores it in
> `proposed_payload.provisional_id`, and reuses it as the real `modules.id`
> when the request is later approved. This keeps any client-side reference
> that captured the provisional id from the 202 response valid post-approval.
> Same pattern for `create_page` (`provisional_id`).

1. **Agent ID strategy when revoked.** When an agent is revoked, what happens to modules they own? Reassign to user, stay orphaned-but-readable, or soft-delete? Affects FK behavior and the agent-page UX.
2. **Approval-request payload size cap.** Pre-image vs full-payload retention in `audit_blobs`. Set the threshold (suggest 32KB) and a retention policy.
3. **Schema versioning semantics on read.** Does `get_module` echo the row's stored `schema_version` (and migrate lazily for the renderer) or auto-upgrade in place? Pick one (recommend lazy migrate, write-back on next mutation).
4. **`fire_action_button` sync vs async at definition time.** Is mode a property of the `action_target` config (recommended) or chosen per-invocation? Affects whether v1 needs `get_job`.
5. **Iframe allowlist granularity.** Host-only or host+path-prefix? Recommend host+optional-path-prefix. Decide schema before the migration.
6. **MCP transport: HTTP-streamable confirmed.** Implementation cost is real (stdio shim for Claude Desktop fallback). Confirm scope of stdio shim work in Phase 3 or defer.
7. **Pending request TTL.** 7 days proposed. Confirm and decide whether expiration auto-denies (no — separate status `expired`).

### P1 — answer during Phase 2–4

8. **Module ownership transfer.** UI-driven manual transfer in `/settings/pages` or `/settings/agents` — should it exist?
9. **Bulk-approve atomicity.** Per-row recommended; confirm.
10. **Idempotency-key scope.** Per `(agent_id, tool, key)` recommended; confirm.
11. **`update_module` data replace vs JSON-Patch.** Replace wholesale in v1; JSON-Patch variant only if a real use case appears.
12. **Notification dismissal model.** Per-user-session, per-dashboard-instance, or per-agent? Single admin → per-installation is fine.
13. **Chart library.** Recharts in v1. Reconfirm if a single module needs >2000 points.
14. **`table` interactivity.** Read-only display vs client-side sort/filter. Pick before building `<TableModule>`.
15. **Action button parameter matching in rules.** Per-`module_id` or per-action_target_id? Probably per-module_id.
16. **MCP `append_log` batching.** Single-entry first; add `batch_append` only if rate limits bite real workloads.

### P2 — defer until felt

17. **Multi-admin support.** v1 is single admin; if added, `decided_by` becomes a set; affects notification routing.
18. **Agent-initiated rule proposals.** Future ergonomic for batch workflows.
19. **Push of approval decisions to agents.** Future `subscribe_approvals` MCP tool; v1 uses polling.
20. **Cross-resource search endpoint.** `/api/v1/search?q=...` fanning across modules/pages/activity. Useful but not required.
21. **Theme customization.** Accent color, density — defer.
22. **Module version history.** Audit log captures changes; full per-module diff viewer is v2.
23. **Multi-page module placement.** Each placement = separate module in v1.
24. **Activity export format.** JSON/CSV/NDJSON — wait for a real use case.
25. **Realtime ring buffer per-topic policy.** Defaults are fine; tune empirically.

### Risks

- **SQLite single-writer choke.** Mitigation: every write goes through FastAPI (one process). If the MCP server ever spawns aggressive concurrent workers, that's where contention shows up; the `busy_timeout=5000` cushions it but watch SQLITE_BUSY in logs.
- **Tool description token bloat.** 11 tools × 400 tokens = 4.4K tokens per agent turn. Real risk to context budget for LLM-driven agents. Mitigation: discipline on description length; verbose docs in `get_module_schema`.
- **Approval queue UX collapse under spammy agents.** Mitigation: per-agent write rate limiting + queue caps + (Phase 6) rule-suggestion banner.
- **`@rjsf/core` bundle weight.** ~80KB gzipped including ajv. Acceptable for an admin tool; not for a public site.
- **iframe allowlist accidental opening.** A loose pattern (`*.example.com`) embeds anything subdomain-takeoverable. Mitigation: prefer host-only allowlist, document the risk in the UI.
- **Lost audit trail on revoked agent.** Agents are never deleted, only revoked, to keep audit FKs honest. Document this; design the UI to display revoked agents in muted styling rather than hiding them.
- **MCP transport mismatch with some clients.** If Claude Desktop or another local-only client doesn't grow HTTP-streamable support, the stdio shim is the only bridge — keep it minimal but maintained.

---

## Appendix A — Module action_type ⇄ approval flow quick reference

| MCP tool | action_type | Default outcome (owner) | Default outcome (non-owner) |
|---|---|---|---|
| `propose_module` | `create_module` | prompt | prompt |
| `update_module` (data only) | `update_module_data` | auto_approve | prompt |
| `update_module` (config) | `update_module_config` | prompt | prompt |
| `update_module` (title/position/permissions) | `update_module_meta` | prompt | prompt |
| `delete_module` | `delete_module` | prompt | prompt |
| `propose_page` | `create_page` | prompt | prompt |
| (admin only) | `delete_page` | n/a | prompt |
| `fire_action` | `fire_action_button` | prompt | prompt |
| `append_log` | `update_module_data` (special-cased) | auto_approve | prompt |

---

## Appendix B — Pre-flight checklist before Phase 1

- [ ] Confirm SQLite ≥ 3.35 available in the deployment image.
- [ ] Decide the P0 open questions above (1–7).
- [ ] Reserve Tailscale hostname (`homebase.<tailnet>.ts.net`).
- [ ] Generate initial admin password + service secret + signed-cookie secret.
- [ ] Choose backup target (filesystem snapshot vs `sqlite3 .backup` to a separate drive).
- [ ] Confirm Caddy config: HTTP/2 on, `flush_interval -1` for SSE paths, idle timeouts ≥ a few minutes.
