# pdash MCP server

Translation layer between MCP clients (AI agents) and the Home Base backend.

## Run

From the **repo root** (recommended):

```bash
make setup   # once
make dev     # starts backend + MCP + frontend
```

MCP-only after `make setup` (reads `../.env`):

```bash
cd mcp
.venv/bin/python -m app.main
```

Default URL: http://127.0.0.1:8090/mcp

See [docs/dev.md](../docs/dev.md), `scripts/run.sh`, and `scripts/smoke.py`.
