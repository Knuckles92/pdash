# pdash

Self-hosted personal command center and agent integration surface. Tailscale-only;
not for public internet exposure.

## Quickstart (local development)

```bash
cp .env.development.example .env
make setup    # venvs, npm, DB at data/pdash.db, secrets in .env
make dev      # backend + MCP + frontend with hot reload
```

Open [http://localhost:3000](http://localhost:3000) (default password `dev`). Full guide: [docs/dev.md](docs/dev.md).

## Production (homelab)

```bash
cp .env.example .env       # fill in PDASH_BOOTSTRAP_ADMIN_PASSWORD
make init                  # initialize the SQLite DB + secrets (Docker)
make prod                  # docker compose up -d
```

See [docs/deploy.md](docs/deploy.md) for Tailscale TLS wiring and backups.

## Layout

| Path | What |
|---|---|
| `PLAN.md` | Full design + roadmap. Start here. |
| `backend/` | FastAPI app, SQLite, Alembic migrations, approval engine. |
| `mcp/` | MCP server (HTTP-streamable) — thin translator over `/api/v1/internal/*`. |
| `frontend/` | Next.js admin UI (App Router). |
| `docs/` | Dev guide, deployment guide, smoke-test recipes. |
| `scripts/` | `setup-dev.sh`, `dev.sh`, `backup.sh`. |
| `Caddyfile` | Reverse proxy in front of all three services. |
| `docker-compose.yml` | Production stack (backend / mcp / frontend / caddy). |

## Common commands

```bash
make setup             # one-time dev bootstrap
make dev               # native dev stack (hot reload)
make test              # backend pytest + mcp pytest + frontend typecheck/build
make prod              # production docker compose up -d
make build             # build all three Docker images
make backup            # snapshot data/pdash.db (rotation built-in)
make logs              # tail compose logs
```

Single admin, single tenant, single-writer SQLite. Designed for
homelab-scale workloads.
