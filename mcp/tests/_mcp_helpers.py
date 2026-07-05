"""Helpers for invoking MCP tools in tests without spinning up the
streamable-HTTP transport.

The tools call ``_require_agent(ctx)`` which inspects
``ctx.request_context.request`` (a Starlette Request) for the Authorization
header. We stub that out with a minimal fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp.server.fastmcp import FastMCP


@dataclass
class _FakeRequest:
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class _FakeRequestContext:
    """Minimal stand-in for mcp.shared.context.RequestContext."""

    request: _FakeRequest
    request_id: str = "test-req"
    meta: None = None
    session: Any = None
    lifespan_context: Any = None
    experimental: Any = None
    close_sse_stream: Any = None
    close_standalone_sse_stream: Any = None


def context_for(mcp: FastMCP, *, agent_key: str | None) -> Any:
    """Construct a Context the tool layer will accept."""
    from mcp.server.fastmcp.server import Context

    headers: dict[str, str] = {}
    if agent_key is not None:
        headers["authorization"] = f"Bearer {agent_key}"
    req = _FakeRequest(headers=headers)
    rc = _FakeRequestContext(request=req)
    return Context(request_context=rc, fastmcp=mcp)


async def call_tool(mcp: FastMCP, name: str, arguments: dict[str, Any], *, agent_key: str | None):
    """Invoke a tool with a stub agent context. Returns the tool's raw
    return value (NOT the MCP wire-format ContentBlock sequence).

    Errors raised inside the tool surface as ``ToolError`` (FastMCP wraps
    every tool exception). The original McpError is the ``__cause__``.
    """
    ctx = context_for(mcp, agent_key=agent_key)
    tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001
    assert tool is not None, f"unknown tool: {name}"
    return await tool.run(arguments, context=ctx, convert_result=False)


def unwrap_mcp_error(exc: BaseException):
    """Pull the original McpError out of a ToolError wrapper, if present."""
    from mcp import McpError
    cur: BaseException | None = exc
    while cur is not None:
        if isinstance(cur, McpError):
            return cur
        cur = cur.__cause__
    return None


def build_mcp_for_tests() -> FastMCP:
    """A FastMCP with all tools registered (no transport binding)."""
    from app.main import build_server
    return build_server()
