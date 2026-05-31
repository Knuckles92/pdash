# Local development guide

Native processes with hot reload — no Docker required for day-to-day work.
Production / homelab deploy is documented in [deploy.md](deploy.md).

## Prerequisites

- **Python 3.12** (`python3.12` on `PATH`)
- **Node.js 22** (for the Next.js frontend)
- **npm** (ships with Node)

## First-time setup

```bash
cp .env.development.example .env
make setup
```

`make setup` will:

1. Create `backend/.venv` and `mcp/.venv` and install editable dependencies.
2. Run `npm ci` in `frontend/`.
3. Initialize `data/pdash.db` if missing (admin password defaults to `dev` via `PDASH_DEV_ADMIN_PASSWORD`).
4. Write `PDASH_SERVICE_SECRET` into `.env` automatically.

Change the dev password by editing `PDASH_DEV_ADMIN_PASSWORD` in `.env` **before** the first `make setup`, or delete `data/pdash.db` and re-run setup.

## Daily workflow

```bash
make dev          # backend (:8080) + MCP (:8090) + UI (:3000)
```

Open [http://localhost:3000](http://localhost:3000) and sign in with your dev password (default `dev`).

Fresh installs seed **example dashboard tiles** on Home and **three pending approval requests** in the Approvals inbox (demo agent “Home Bot”). They are safe to deny; approving applies real changes. After editing seed data in `backend/app/seed_home.py` or `backend/app/seed_approvals.py`, refresh a running dev database without wiping it:

```bash
backend/.venv/bin/python backend/scripts/reseed_home.py --db data/pdash.db
make reseed-approvals   # or: backend/.venv/bin/python backend/scripts/reseed_approvals.py --db data/pdash.db
```

Refresh the dashboard / Approvals page in the browser after reseeding (direct SQL does not emit SSE).

Stop the stack with **Ctrl+C** in the terminal running `make dev`, or from another shell:

```bash
make dev-stop
```

Logs are written under `.dev/logs/`:

```bash
tail -f .dev/logs/backend.log .dev/logs/mcp.log .dev/logs/frontend.log
```

## Tests

```bash
make test
```

Requires `make setup` first (creates `backend/.venv` and `mcp/.venv`).

## Configuration

All services read the repo-root `.env` (see `.env.development.example`). Important variables:

| Variable | Dev default | Notes |
|----------|-------------|-------|
| `PDASH_DATABASE_PATH` | `data/pdash.db` (absolute after setup) | Shared with `make prod` Docker volume |
| `PDASH_COOKIE_SECURE` | `false` | Must be `true` behind HTTPS in production |
| `PDASH_SERVICE_SECRET` | auto-filled by setup | MCP → backend internal auth |
| `PDASH_DEV_ADMIN_PASSWORD` | `dev` | Only used by `make setup`; not read by apps |
| `PDASH_BACKEND_URL` | `http://127.0.0.1:8080` | Next.js rewrites and MCP client |

Backend and MCP also load `../.env` when run from their package directories.

## Running a single service

With `.env` in place:

```bash
# Backend only
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8080

# MCP only
cd mcp && .venv/bin/python -m app.main

# Frontend only (needs backend on :8080)
cd frontend && npm run dev
```

Or use `scripts/lib/load-env.sh` from custom scripts:

```bash
source scripts/lib/load-env.sh && load_pdash_env
```

## Troubleshooting

### Login fails / session not sticking

- Ensure `PDASH_COOKIE_SECURE=false` in `.env` for plain HTTP localhost.
- Use the UI at `http://localhost:3000` (not the backend port directly).

### `PDASH_SERVICE_SECRET is empty`

Run `make setup` again on a fresh DB, or paste the secret from a prior `python -m app.cli init` into `.env`.

### Port already in use

Stop a previous `make dev` (`make dev-stop`) or find the process on 3000 / 8080 / 8090.

### `setup-dev: refusing … PDASH_COOKIE_SECURE=true`

You copied `.env.example` (production) instead of `.env.development.example`. Use the development template or set `PDASH_ENV=production` only if intentional.

### Database reset

```bash
rm -f data/pdash.db data/pdash.db-*
make setup
```

## Production

For Docker + Caddy + Tailscale on a homelab host:

```bash
cp .env.example .env   # production template
make init              # or follow docs/deploy.md
make prod
```

See [deploy.md](deploy.md) for TLS, backups, and upgrades.
