"""End-to-end smoke test of the running MCP server.

Usage::

    cd mcp
    .venv/bin/python scripts/smoke.py \
        --mcp-url http://127.0.0.1:8090/mcp \
        --agent-key hb_agt_...

What it does:

1. Lists tools (expects 11).
2. Calls get_module_schema(markdown).
3. Calls propose_module (markdown on home) — expects pending.
4. Polls list_my_pending_requests — sees the request.

Out-of-band: an admin approves the request via curl; rerun the script
afterwards and notice get_module returns the materialised module.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main(mcp_url: str, agent_key: str) -> int:
    headers = {"Authorization": f"Bearer {agent_key}"}
    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            print(f"[1] tool count: {len(tools)}")
            for t in tools:
                print(f"    - {t.name}")

            schema = await session.call_tool("get_module_schema", {"type": "markdown"})
            print(f"[2] get_module_schema(markdown) ok: isError={schema.isError}")

            # NOTE: caller must supply a real page_id; we discover via list_pages.
            pages = await session.call_tool("list_pages", {"limit": 5})
            pages_struct = pages.structuredContent
            page_id = None
            if isinstance(pages_struct, dict) and pages_struct.get("items"):
                page_id = pages_struct["items"][0]["id"]
            if not page_id:
                print("    no pages discoverable for this agent — pre-create one as admin")
                return 1

            propose = await session.call_tool(
                "propose_module",
                {
                    "page_id": page_id,
                    "type": "markdown",
                    "title": "smoke",
                    "data": {"body": "# smoke"},
                    "config": {},
                },
            )
            print(f"[3] propose_module: {json.dumps(propose.structuredContent, indent=2)}")

            pending = await session.call_tool("list_my_pending_requests", {})
            print(f"[4] list_my_pending_requests: {json.dumps(pending.structuredContent, indent=2)}")

    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mcp-url", default="http://127.0.0.1:8090/mcp")
    p.add_argument("--agent-key", required=True)
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.mcp_url, args.agent_key)))
