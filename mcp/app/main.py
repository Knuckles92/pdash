"""MCP server entry point.

Run with::

    PDASH_SERVICE_SECRET=...  python -m app.main

The streamable-HTTP transport is mounted at ``/mcp`` (FastMCP default), so
the URL is ``http://<host>:<port>/mcp``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

from mcp.server.fastmcp import FastMCP

from . import decision_cache
from .backend import close_client, get_client
from .health import register_health_routes
from .settings import get_settings
from .tools import register_tools

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _coerce_log_level(level: str) -> LogLevel:
    normalized = level.upper()
    match normalized:
        case "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL":
            return normalized
        case _:
            return "INFO"


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@asynccontextmanager
async def _lifespan(_: FastMCP) -> AsyncIterator[None]:
    """Start the decision-cache SSE subscriber on startup, stop on shutdown."""
    decision_cache.start_subscription()
    try:
        yield None
    finally:
        await decision_cache.stop_subscription()


def build_server() -> FastMCP:
    """Construct a FastMCP instance with all tools registered."""
    settings = get_settings()
    mcp = FastMCP(
        name="pdash",
        instructions=(
            "pdash MCP server. First add this server to your MCP client "
            "configuration (streamable HTTP, no Authorization header). If you have no "
            "hb_agt_ API key, call 'onboarding' for the full setup flow, then "
            "'request_registration' to ask the admin for access and "
            "'claim_registration' to pick up your key once approved — those three tools "
            "need no key; every other tool does until you update your MCP config with "
            "the key. Use MCP tools, not raw HTTP. All write tools route through the "
            "approval engine; responses use status=applied/pending/denied. Call "
            "get_module_schema before propose_module. Do NOT retry pending responses; "
            "poll list_my_pending_requests instead. Honor retry_after_ms on rate-limit "
            "errors."
        ),
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=_coerce_log_level(settings.log_level),
        streamable_http_path="/mcp",
        stateless_http=True,  # one HTTP request per tool call; no persistent session state
        json_response=True,   # plain JSON responses, no SSE multiplexing for tool replies
        lifespan=_lifespan,
    )
    register_tools(mcp)
    register_health_routes(mcp)
    return mcp


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = logging.getLogger(__name__)

    if not settings.service_secret:
        log.error(
            "PDASH_SERVICE_SECRET is empty — set it to the value printed by "
            "the backend's `python -m app.cli init`."
        )
        raise SystemExit(2)

    log.info(
        "pdash-mcp starting on http://%s:%d/mcp -> %s",
        settings.mcp_host,
        settings.mcp_port,
        settings.backend_url,
    )

    mcp = build_server()
    # Force the singleton client to warm up so misconfig surfaces early.
    _ = get_client()
    try:
        mcp.run(transport="streamable-http")
    finally:
        # Best-effort close
        try:
            import anyio
            anyio.run(close_client)
        except Exception:
            pass


if __name__ == "__main__":
    main()
