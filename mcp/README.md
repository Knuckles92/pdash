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

In production both paths are served through Caddy, so an agent on another
tailnet device connects to `https://<host>.<tailnet>.ts.net/mcp` (and reads the
skill file at `.../mcp-skill/SKILL.md`). The MCP server itself always runs next
to the backend — same host, same compose network; running it elsewhere is
unsupported. See "Connecting remote agents" in `docs/deploy.md`.

See `scripts/run.sh` and `scripts/smoke.py`.
