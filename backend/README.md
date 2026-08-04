# pdash backend (Phase 1)

FastAPI service for pdash. Phase 1 ships:

- Bootstrap CLI (`python -m app.cli init …`).
- Admin auth (signed-cookie session + double-submit CSRF + progressive throttle).
- Module / page / agent / iframe-allowlist / action-target CRUD endpoints (admin path).
- Module schema registry: nine module types as Pydantic models with a JSON Schema endpoint.
- SQLite (WAL) with tables, indexes and CHECK constraints applied by Alembic migrations.
- Seeds: the `pages.home` row and the nine built-in `approval_rules`.
- `/healthz`, `/readyz` (no DB ping), and a session-gated Swagger UI at `/api/v1/docs`.
- RFC 7807 `application/problem+json` errors with stable `code` strings.
- Pytest harness covering auth, modules, pages, agents, schemas, and idempotency replay.

## Why `pyproject.toml` (not `requirements.txt`)?

Editable installs (`pip install -e .`) work for both the application and the test suite without
maintaining two dependency lists. Pinned-major versions are recorded directly in
`pyproject.toml`'s `[project.dependencies]` and `[project.optional-dependencies.dev]`.

## Quick start

From the **repo root** (recommended):

```bash
cp .env.development.example .env
make setup
make dev
```

Or backend-only after `make setup`:

```bash
cd backend
PDASH_DATABASE_PATH=../data/pdash.db \
  .venv/bin/uvicorn app.main:app --reload --port 8080

# In another shell:
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"dev"}' -c cookies.txt

CSRF=$(grep csrf_token cookies.txt | awk '{print $7}')

# List all 9 module schemas:
curl http://localhost:8080/api/v1/module-schemas -b cookies.txt

# Get the home page:
curl http://localhost:8080/api/v1/pages -b cookies.txt

# Create a module (state change → needs CSRF header):
curl -X POST http://localhost:8080/api/v1/modules \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $CSRF" \
  -b cookies.txt \
  -d '{
    "type": "markdown",
    "page_id": "'"$(curl -s http://localhost:8080/api/v1/pages -b cookies.txt | python -c 'import json,sys;print(next(p["id"] for p in json.load(sys.stdin)["items"] if p["slug"]=="home"))')"'",
    "data": {"body":"# hello"},
    "config": {}
  }'
```

## Tests

```bash
cd backend
.venv/bin/pytest
```

Each test starts on a fresh SQLite file under `/tmp/pdash-test-…`. Migrations and admin
bootstrap run from inside the `initialized_db` fixture; the `admin_client` fixture returns
a logged-in `TestClient` with its `X-CSRF-Token` header already wired up.

## Configuration

All env vars are prefixed `PDASH_`:

| Var | Default | Notes |
|---|---|---|
| `PDASH_DATABASE_PATH` | — | Absolute path to the SQLite file. Overrides `PDASH_DATABASE_URL`. |
| `PDASH_DATABASE_URL` | `sqlite+aiosqlite:///./pdash.db` | SQLAlchemy async URL. |
| `PDASH_COOKIE_SECURE` | `false` | Set to `true` in production (Caddy/HTTPS). |
| `PDASH_SESSION_LIFETIME_SECONDS` | `2592000` | 30-day sliding session. |
| `PDASH_AUDIT_BLOB_THRESHOLD_BYTES` | `32768` | 32 KB; payloads above this spill to `audit_blobs` (P0). |
| `PDASH_PENDING_TTL_SECONDS` | `604800` | 7-day pending TTL (P0). |
| `PDASH_AGENT_REGISTRATION_MAX_PENDING` | `25` | Max outstanding pending agent self-registrations before new ones are refused (bounds the ungated bootstrap path). |
| `PDASH_AGENT_REGISTRATION_TTL_SECONDS` | `604800` | 7-day claimable window for a pending agent self-registration before it expires. |
| `PDASH_LOG_JSON` | `false` | JSON-format structured logs. |
| `PDASH_LOG_LEVEL` | `INFO` | |
| `PDASH_DOCS_ENABLED` | `true` | Mount session-gated Swagger UI at `/api/v1/docs`. |

## P0 decisions encoded

1. **Revoked agents** → `agents.status='revoked'`; their modules remain queryable and un-mutatable via the agent path (the agent path doesn't exist yet — admin can still touch them).
2. **Audit blob threshold** → 32 KB, configurable. Spillover writes to `audit_blobs`.
3. **Schema versioning** → `modules.schema_version` column exists. Lazy migrate-on-read + write-back-on-mutation is wired into the data model; migration registry implementation is deferred to Phase 3 when first-version bumps happen.
4. **`fire_action` sync/async** → `action_targets.mode` column (`sync`/`async`).
5. **Iframe allowlist** → `iframe_allowlist.host_pattern` + optional `path_prefix`.
6. **MCP transport** → HTTP-streamable only (deferred to Phase 3).
7. **Pending TTL** → 7 days, distinct `expired` status.

## What's NOT here yet (per Phase 1 scope)

- Approval engine + decision endpoints — Phase 3.
- `/api/v1/internal/*` endpoints — Phase 3.
- MCP server process — Phase 3.
- Realtime SSE / EventBus — Phase 5.
- Frontend (Next.js) — Phases 2/4.
- Action-target dispatcher (webhook, local_script, etc.) — Phase 4 (the `POST /action-targets/{id}/test` endpoint currently validates only).

Look for `TODO Phase N` markers in code where a hook is wired but unimplemented.
