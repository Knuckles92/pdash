"""Custom HTTP routes for health checks and admin status.

FastMCP serves the MCP protocol at ``/mcp`` but also lets us register plain
HTTP routes via :meth:`FastMCP.custom_route`. We expose three:

- ``GET /healthz`` — open liveness probe (used by Docker healthchecks). Mirrors
  the backend convention of returning ``{"status": "ok"}``.
- ``GET /mcp-skill/SKILL.md`` — open agent bootstrap instructions in the
  standard skill-file shape. Contains no secrets.
- ``GET /info`` — service-secret–gated metadata for the admin "MCP control
  center" in the web UI: version, backend connectivity, SSE-stream state, and
  the categorized tool catalog. Gated so the tool list never sits on an
  unauthenticated route (``custom_route`` itself skips MCP auth).

The backend's ``GET /api/v1/mcp/status`` endpoint probes ``/info`` and forwards
the result to the frontend.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import __version__, decision_cache
from .onboarding import skill_markdown
from .settings import get_settings
from .tools import BOOTSTRAP_TOOLS, WRITE_TOOLS

# Catalog sort order by category (write first, ungated bootstrap last).
_CATEGORY_RANK = {"write": 0, "read": 1, "bootstrap": 2}


def _categorize(name: str) -> str:
    if name in WRITE_TOOLS:
        return "write"
    if name in BOOTSTRAP_TOOLS:
        return "bootstrap"
    return "read"


def register_health_routes(mcp) -> None:
    """Register custom HTTP routes on the FastMCP server."""

    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    @mcp.custom_route("/mcp-skill/SKILL.md", methods=["GET"], include_in_schema=False)
    async def mcp_skill(request: Request) -> Response:
        mcp_url = str(request.url.replace(path="/mcp", query=""))
        return Response(
            skill_markdown(mcp_url),
            headers={
                "content-type": "text/markdown; charset=utf-8",
                "access-control-allow-origin": "*",
            },
        )

    @mcp.custom_route("/info", methods=["GET"], include_in_schema=False)
    async def info(request: Request) -> Response:
        settings = get_settings()
        secret = settings.service_secret
        # Require the shared service secret. Empty secret means misconfigured —
        # treat as unauthorized rather than open the route.
        provided = request.headers.get("authorization", "")
        expected = f"Bearer {secret}" if secret else None
        if expected is None or provided != expected:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        tools = []
        for tool in await mcp.list_tools():
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "category": _categorize(tool.name),
                }
            )
        tools.sort(key=lambda t: (_CATEGORY_RANK.get(t["category"], 9), t["name"]))

        return JSONResponse(
            {
                "name": "pdash",
                "version": __version__,
                "backend_url": settings.backend_url,
                "auth_cache_ttl_s": settings.auth_cache_ttl_s,
                "idem_dedupe_ttl_s": settings.idem_dedupe_ttl_s,
                "sse_connected": decision_cache.is_connected(),
                "last_event_id": decision_cache.last_event_id(),
                "tools": tools,
            }
        )
