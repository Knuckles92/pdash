# pdash MCP server

Translation layer between MCP clients (AI agents) and the pdash backend.

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

Fresh agents can read the hosted standard skill file before they know how to use
the MCP tools:

```text
http://127.0.0.1:8090/mcp-skill/SKILL.md
```

The skill route is unauthenticated and contains only setup guidance. It points
the agent at the sibling `/mcp` endpoint, then walks through
`onboarding` -> `request_registration` -> admin approval -> `claim_registration`.

See `scripts/run.sh` and `scripts/smoke.py`.
