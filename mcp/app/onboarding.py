"""Shared agent-onboarding guidance for tools and hosted skill files."""

from __future__ import annotations

from typing import Any


def onboarding_payload() -> dict[str, Any]:
    """Return the structured guidance used by the ungated onboarding tool."""
    return {
        "service": "pdash - a self-hosted dashboard you publish modules to.",
        "auth_model": (
            "Add this MCP server to your client's MCP configuration first (streamable HTTP, "
            "no Authorization header). Three tools work without a key: onboarding, "
            "request_registration, claim_registration. Every other tool requires an agent "
            "API key (hb_agt_...) in your MCP config headers as "
            "'Authorization: Bearer <key>' after registration completes."
        ),
        "steps": [
            "1. Add this MCP server to your client's MCP configuration (streamable HTTP URL "
            "ending in /mcp, no Authorization header) and reload so pdash tools are available. "
            "Use MCP tool calls - not raw curl/WebFetch/JSON-RPC endpoint probing - unless "
            "debugging.",
            "2. Call request_registration(display_name=...) with a clear name for yourself "
            "(optionally description + rationale). This creates a PENDING request; it does "
            "not grant access.",
            "3. Save the returned claim_token. Ask the human to approve you in pdash under "
            "Settings -> Agents. You cannot self-approve.",
            "4. Poll claim_registration(claim_token=...) about every 10s. While pending it "
            "returns status='pending'. Do NOT call request_registration again.",
            "5. When status='approved', save the returned api_key (shown once). Update your "
            "MCP client config to add 'Authorization: Bearer <api_key>' in headers and "
            "reconnect - the full tool set is now unlocked.",
        ],
        "notes": [
            "Gated tools return auth_required until step 5 completes - that is expected.",
            "Writes flow through an approval engine: tool results use "
            "status=applied|pending|denied. Never retry a 'pending' write - poll "
            "list_my_pending_requests instead.",
            "Once registered, call whoami and get_module_schema to learn your permissions "
            "and the module shapes.",
        ],
    }


def skill_markdown(mcp_url: str) -> str:
    """Render the standard SKILL.md served to fresh agents."""
    description = (
        "Connect to pdash, a self-hosted dashboard exposed over MCP. "
        "Use when an AI agent needs to configure the pdash MCP server, request "
        "keyless registration, claim its hb_agt_ API key after admin approval, "
        "or safely publish/read dashboard modules through pdash tools."
    )
    return f"""---
name: pdash-onboarding
description: {description}
---

# pdash Onboarding

Use this skill when connecting to pdash. pdash is a self-hosted
dashboard that agents update through MCP tools. You must configure the MCP
server before using pdash tools.

## Connect

Add this streamable HTTP MCP server to your client configuration with no
Authorization header:

```json
{{
  "mcpServers": {{
    "pdash": {{
      "url": "{mcp_url}"
    }}
  }}
}}
```

Reload or restart your MCP session so the pdash tools appear. Do not call the
MCP endpoint with raw curl, WebFetch, or hand-written JSON-RPC unless you are
debugging transport setup. Use MCP tool calls through your client.

## Register

If you do not have an `hb_agt_` API key, use only the three ungated tools:
`onboarding`, `request_registration`, and `claim_registration`.

1. Call `onboarding` to confirm the connection.
2. Call `request_registration` exactly once with a clear `display_name`.
   Include `description`, `rationale`, and `client_hint` when useful.
3. Save the returned `claim_token`. It is shown once and is not the API key.
4. Tell the human admin that the request is pending in Settings -> Agents.
5. Poll `claim_registration(claim_token="...")` about every 10 seconds.
   Do not call `request_registration` again while waiting.
6. When `claim_registration` returns `status="approved"`, save the returned
   `api_key`. It is shown once.

After approval, update the same MCP server config:

```json
{{
  "mcpServers": {{
    "pdash": {{
      "url": "{mcp_url}",
      "headers": {{ "Authorization": "Bearer hb_agt_..." }}
    }}
  }}
}}
```

Reconnect after adding the bearer token.

## Work Safely

- Gated tools returning `auth_required` before registration is complete is
  expected.
- Every write goes through the admin approval engine and returns
  `status="applied"`, `status="pending"`, or `status="denied"`.
- Never retry a write that returned `pending`; poll `list_my_pending_requests`
  instead.
- Call `whoami` after reconnecting to verify the active agent and permissions.
- Call `get_module_schema` before `propose_module` or unfamiliar module updates.
- Honor `retry_after_ms` on rate limits and back off on service errors.
"""


__all__ = ["onboarding_payload", "skill_markdown"]
