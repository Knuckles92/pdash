# pdash — convenience tasks.
# Local development and production docker-compose helpers.

SHELL := bash
.ONESHELL:

.PHONY: help setup dev dev-stop prod init down build test test-backend test-mcp test-frontend backup logs check-venvs reseed-approvals

help:
	@echo "Targets:"
	@echo "  make setup          Dev bootstrap (venvs, npm, DB, .env secrets)"
	@echo "  make dev            Native stack with hot reload (backend + mcp + frontend)"
	@echo "  make dev-stop       Stop processes recorded by make dev"
	@echo "  make prod           Production docker compose up -d"
	@echo "  make down           docker compose down"
	@echo "  make init           First-time prod bootstrap via Docker (prompts for password)"
	@echo "  make build          Build all three Docker images"
	@echo "  make test           Run backend + mcp + frontend test suites"
	@echo "  make test-backend   Backend pytest only"
	@echo "  make test-mcp       MCP pytest only"
	@echo "  make test-frontend  Frontend typecheck + build"
	@echo "  make backup         Snapshot data/pdash.db to data/backups/"
	@echo "  make logs           Tail all compose logs"
	@echo "  make reseed-approvals  Rewrite example pending approvals in data/pdash.db"

setup:
	./scripts/setup-dev.sh

dev:
	./scripts/dev.sh

dev-stop:
	./scripts/dev-stop.sh

prod:
	docker compose up -d

down:
	docker compose down

init:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env — edit it and re-run."; exit 1; fi
	@read -r -p "Admin password: " PASSWORD; \
	  docker compose run --rm \
	    -e PDASH_BOOTSTRAP_ADMIN_PASSWORD="$$PASSWORD" \
	    backend python -m app.cli init --admin-password "$$PASSWORD"

build:
	docker compose build

check-venvs:
	@test -x backend/.venv/bin/pytest || { echo "Run 'make setup' first (missing backend/.venv)."; exit 1; }
	@test -x mcp/.venv/bin/pytest || { echo "Run 'make setup' first (missing mcp/.venv)."; exit 1; }

test: check-venvs test-backend test-mcp test-frontend

test-backend: check-venvs
	cd backend && .venv/bin/pytest -q

test-mcp: check-venvs
	cd mcp && .venv/bin/pytest -q

test-frontend:
	cd frontend && npm run typecheck && npm run build

backup:
	./scripts/backup.sh

logs:
	docker compose logs -f --tail=200

reseed-approvals: check-venvs
	cd backend && .venv/bin/python scripts/reseed_approvals.py --db ../data/pdash.db
