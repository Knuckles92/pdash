"""MCP tool definitions.

The agent-facing tools (the write/read set from PLAN §6 plus the visibility +
self-diagnosis tools), registered on a :class:`FastMCP` server. Each tool:

1. Extracts the calling agent from the MCP request's Authorization header.
2. Validates its arguments against a Pydantic model.
3. Delegates to :mod:`app.backend` for the actual HTTP call.
4. Maps :class:`~app.backend.BackendError` to either MCP transport errors
   (auth, rate limit, not found, conflict, service-unavailable) or
   payload-level outcomes (``denied``, ``application_failed``).

**Payload-level ``denied`` is not an MCP error** — the call was structurally
valid; only the approval rule refused. The agent reads ``reason`` and
decides what to do.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from mcp import McpError, types as mcp_types
from mcp.server.fastmcp import Context, FastMCP, Image
from pydantic import BaseModel, ConfigDict, Field

from . import auth as auth_mod
from . import decision_cache, idem
from .backend import AgentInfo, BackendError, get_client
from .onboarding import onboarding_payload

logger = logging.getLogger(__name__)


# Tools whose calls route through the approval engine (write side). Every other
# registered tool is read-only. Used by ``app.health`` to categorize the tool
# catalog for the admin control center.
WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "propose_module",
        "update_module",
        "delete_module",
        "propose_page",
        "fire_action",
        "append_log",
        "register_file",
    }
)


# Ungated onboarding tools: callable WITHOUT an agent API key so a brand-new
# client can learn how to connect and request its first registration. They never
# mutate dashboard state and never mint a key on their own (registration is
# always admin-approved). ``app.health`` labels these ``bootstrap`` in the
# catalog so the admin can see exactly which tools need no key.
BOOTSTRAP_TOOLS: frozenset[str] = frozenset(
    {
        "onboarding",
        "request_registration",
        "claim_registration",
    }
)


# ---------------------------------------------------------------------------
# Argument models (one per tool)
# ---------------------------------------------------------------------------


class ProposeModuleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    type: str
    title: str | None = Field(default=None, max_length=200)
    data: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] | None = None
    idempotency_key: str | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class UpdateModuleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    data: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    title: str | None = Field(default=None, max_length=200)
    position: int | None = None
    expected_version: int | None = None
    idempotency_key: str | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class DeleteModuleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    expected_version: int | None = None
    idempotency_key: str | None = None
    reason: str | None = Field(default=None, max_length=1000)


class ProposePageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,40}$")
    description: str | None = Field(default=None, max_length=500)
    type: Literal["agent", "canvas"] = "agent"
    idempotency_key: str | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class FireActionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str  # the action_button module (server resolves to action_target_id)
    target_id: str | None = None  # optional override for direct action_target invocations
    payload: dict[str, Any] | None = None
    idempotency_key: str | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: str | None = None
    level: str | None = None
    message: str = Field(..., max_length=2000)
    fields: dict[str, Any] | None = None


class AppendLogArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    entry: LogEntry
    idempotency_key: str | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class ListMyModulesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str | None = None
    type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class GetModuleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str


class ListPagesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class ListMyPendingRequestsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_filter: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class GetModuleSchemaArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str


class ValidateModuleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class ModuleHealthArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str | None = None
    only_broken: bool = False
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class RenderPageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str


class ScreenshotPageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    viewport_width: int | None = Field(default=None, ge=360, le=3840)
    full_page: bool = True


class GetFileDropboxArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str | None = None


class RegisterFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbox_name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=200)
    page_id: str | None = None
    purpose: str | None = Field(default=None, max_length=1000)
    idempotency_key: str | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class ListMyFilesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class RequestRegistrationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    rationale: str | None = Field(default=None, max_length=1000)
    client_hint: str | None = Field(default=None, max_length=200)


class ClaimRegistrationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_token: str = Field(..., min_length=8, max_length=200)
    registration_id: str | None = None


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------

# MCP standard JSON-RPC error codes (defined in spec; libraries don't export
# them as constants).
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
# Server-defined range starts at -32000 per JSON-RPC. We use these for
# domain-mapped errors so clients can distinguish them.
_AUTH_REQUIRED = -32001
_NOT_FOUND = -32002
_CONFLICT = -32003
_RATE_LIMIT = -32004
_SERVICE_UNAVAILABLE = -32005
_AGENT_DISABLED = -32006


def _mcp_error(code: int, message: str, *, data: dict[str, Any] | None = None) -> McpError:
    return McpError(mcp_types.ErrorData(code=code, message=message, data=data or {}))


def _backend_error_to_mcp(exc: BackendError) -> McpError:
    """Translate non-payload-level backend errors to McpError."""
    code = exc.code
    # Auth
    if code.startswith("auth.") or exc.status in (401,):
        return _mcp_error(
            _AUTH_REQUIRED,
            exc.detail or "authentication failed",
            data={"backend_code": code, "status": exc.status},
        )
    if code == "agent.disabled":
        return _mcp_error(
            _AGENT_DISABLED,
            "calling agent is not active",
            data={"backend_code": code},
        )
    if code == "agent.unknown":
        return _mcp_error(
            _AUTH_REQUIRED,
            "agent not recognized",
            data={"backend_code": code},
        )
    if exc.status == 404 or code.endswith(".not_found"):
        return _mcp_error(
            _NOT_FOUND,
            exc.detail or "not found",
            data={"backend_code": code},
        )
    if exc.status == 412 or code == "concurrency.stale":
        return _mcp_error(
            _CONFLICT,
            exc.detail or "version conflict",
            data={"backend_code": code, "hint": "fetch with get_module and retry with current version"},
        )
    if exc.status == 409 or code.endswith(".slug_taken") or code == "idempotency.mismatch":
        return _mcp_error(
            _CONFLICT,
            exc.detail or "conflict",
            data={"backend_code": code},
        )
    if exc.status == 429 or code == "rate_limit.exceeded":
        return _mcp_error(
            _RATE_LIMIT,
            exc.detail or "rate limit exceeded",
            data={"backend_code": code, "retry_after_ms": exc.retry_after_ms},
        )
    if exc.status >= 500 or code == "backend.unreachable":
        return _mcp_error(
            _SERVICE_UNAVAILABLE,
            exc.detail or "backend unavailable",
            data={"backend_code": code, "status": exc.status},
        )
    if exc.status == 400:
        return _mcp_error(
            _INVALID_PARAMS,
            exc.detail or "invalid arguments",
            data={"backend_code": code},
        )
    # Catch-all
    return _mcp_error(
        _INTERNAL_ERROR,
        exc.detail or "unknown error",
        data={"backend_code": code, "status": exc.status},
    )


def _status_envelope(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Translate a backend triad response into the documented MCP envelope.

    PLAN §6: ``{status: applied|pending|denied, request_id?, reason?,
    applied_at?, module?, ...}``. The backend returns ``denied_by_rule``;
    we normalise to ``denied`` for the MCP surface, but preserve ``rule_id``.
    """
    if status_code == 200:
        # Backend already provides request_id, applied_at, module/...; we force
        # the outer status to "applied" (it also reports "applied" itself).
        out: dict[str, Any] = dict(body)
        out["status"] = "applied"
        return out
    if status_code == 202:
        out = dict(body)
        out["status"] = "pending"
        return out
    if status_code == 403:
        # Backend used "denied_by_rule" -> normalise to "denied".
        out = dict(body)
        out["status"] = "denied"
        out["reason"] = body.get("reason") or f"denied by rule {body.get('rule_id')}"
        return out
    if status_code == 500 and body.get("status") == "application_failed":
        out = dict(body)
        out["status"] = "application_failed"
        return out
    # Unexpected — best-effort passthrough.
    return {"status": "unknown", "_http_status": status_code, **body}


# ---------------------------------------------------------------------------
# Backend-call helpers
# ---------------------------------------------------------------------------


async def _call_backend(coro: Any) -> Any:
    """Await a BackendClient coroutine, translating BackendError to McpError."""
    try:
        return await coro
    except BackendError as exc:
        raise _backend_error_to_mcp(exc) from exc


async def _acquire_idem_key(agent_id: str, tool_name: str, args: BaseModel) -> str:
    """Resolve the idempotency key for a write tool call.

    Uses the caller-supplied ``idempotency_key`` if present, otherwise lets
    the dedupe cache mint/reuse one keyed on the remaining args.
    """
    idem_args = args.model_dump(exclude={"idempotency_key"})
    supplied = getattr(args, "idempotency_key", None)
    return await idem.acquire(agent_id, tool_name, idem_args, supplied)


async def _submit_write(agent_id: str, action_type: str, coro: Any) -> dict[str, Any]:
    """Run a module-write backend call and shape the MCP envelope.

    Translates BackendError, wraps the triad response via ``_status_envelope``,
    and records a pending request in the decision cache when applicable.
    """
    status, raw = await _call_backend(coro)
    env = _status_envelope(status, raw)
    if env["status"] == "pending":
        await decision_cache.note_pending(
            agent_id,
            {
                "id": env["request_id"],
                "action_type": action_type,
                "status": "pending",
                "expires_at": env.get("expires_at"),
            },
        )
    return env


# ---------------------------------------------------------------------------
# Agent extraction helper
# ---------------------------------------------------------------------------


async def _require_agent(ctx: Context) -> AgentInfo:
    """Resolve the agent from the MCP request's HTTP context.

    The streamable-HTTP transport exposes the Starlette Request on
    ``ctx.request_context.request``.
    """
    req = None
    try:
        req = ctx.request_context.request  # type: ignore[attr-defined]
    except Exception:
        req = None
    try:
        return await auth_mod.resolve_from_request(req)
    except auth_mod.AuthError as exc:
        raise _mcp_error(_AUTH_REQUIRED, exc.message, data={"code": exc.code}) from exc
    except BackendError as exc:
        # Backend reachable but threw something other than 401 (e.g. 503
        # transport error). Translate the same way regular tool calls do.
        raise _backend_error_to_mcp(exc) from exc


# ---------------------------------------------------------------------------
# Tool descriptions (≤400 tokens each, lifted from PLAN §6)
# ---------------------------------------------------------------------------


_DESC_PROPOSE_MODULE = """\
Create a new module on a page. Use AFTER first calling get_module_schema(type)
to learn the data/config shape; otherwise validation will reject your payload.
Set per-widget color/theme with config.appearance, e.g.
{theme:"tinted", color:"emerald"}.

When to use:
  - Adding a fresh module the agent owns.
  - Never re-call to overwrite an existing module — use update_module instead;
    you'd just end up with a duplicate (or a denied/pending request).

Returns one of:
  - {status:"applied", module_id, module, applied_at, request_id} — rule
    auto-approved and the module is live.
  - {status:"pending", request_id, expires_at} — admin must approve. The
    server already minted a provisional module_id you can reuse on success.
    DO NOT retry; poll list_my_pending_requests instead.
  - {status:"denied", reason, rule_id, request_id} — policy refused. Fix the
    proposal or escalate; retrying as-is will be denied again.

Idempotency:
  - Pass idempotency_key for safe retries. If omitted, the MCP server
    auto-generates one and dedupes rapid retries with the same args for ~60s.

Errors (MCP-level, not payload):
  - auth_required / agent_disabled — re-key or contact admin.
  - not_found (page) — verify page_id with list_pages.
  - invalid_params — schema validation failed; re-fetch with get_module_schema.
  - rate_limit — honor data.retry_after_ms; do not retry sooner.
  - service_unavailable — backend down; retry with backoff.
"""

_DESC_UPDATE_MODULE = """\
Modify an existing module's data, config, title, or position. Wholesale
replace on data/config (pass full new objects, not patches). Per-widget
color/theme lives at config.appearance.

When to use:
  - Updating a module the agent owns. Owner data-only updates typically
    auto-apply via the built-in self-owner rule.
  - Pass expected_version (from get_module/list_my_modules) to safely
    short-circuit if the module has since been edited by someone else.

Returns:
  - {status:"applied", module, applied_at, request_id}
  - {status:"pending", request_id, expires_at} — DO NOT retry.
  - {status:"denied", reason, rule_id, request_id}

Idempotency:
  - Same rules as propose_module. Auto-generated when omitted.

Errors:
  - not_found — module_id is gone or invisible to you.
  - conflict — expected_version stale. Re-fetch with get_module and retry.
  - invalid_params — payload violates the type's schema.
  - rate_limit / service_unavailable — honor retry_after_ms; backoff.
"""

_DESC_DELETE_MODULE = """\
Delete a module (soft-delete, 7-day retention server-side).

When to use:
  - Removing one of your own modules. Defaults to PENDING for admin review;
    rarely auto-applies.

Returns:
  - {status:"applied", request_id, applied_at} — module is gone from views.
  - {status:"pending", request_id, expires_at} — DO NOT retry.
  - {status:"denied", reason, rule_id, request_id}

Idempotency:
  - Pass an idempotency_key to make retries safe. Otherwise auto-generated.

Errors:
  - not_found, conflict (stale expected_version), rate_limit, etc., as for
    update_module. Honor retry_after_ms.
"""

_DESC_PROPOSE_PAGE = """\
Propose a new page (high-friction; nearly always PENDING).

When to use:
  - You need a fresh page to organise your modules. Prefer adding modules to
    an existing page (list_pages) before requesting a new one.

type:
  - "agent" (default) — a normal module grid page.
  - "canvas" — a full-bleed page that renders a single `html` module as an
    app-like surface (sandboxed iframe; no pdash session/API access). After
    the page is approved, propose one `html` module on it — see
    get_module_schema("html") for the injected --pdash-* theme tokens.
    Content updates on html modules always require admin approval.

Returns:
  - {status:"applied", page, request_id, applied_at} — rare.
  - {status:"pending", request_id, expires_at} — DO NOT retry.
  - {status:"denied", reason, rule_id, request_id}

Idempotency: provide a key to safely retry. Honor retry_after_ms.
"""

_DESC_FIRE_ACTION = """\
Fire an action_button — invoke an admin-defined target (webhook, script,
mcp-tool, or agent message) bound to a module.

When to use:
  - Triggering a side-effect the admin has explicitly wired up. Look up the
    module first with get_module to inspect the payload schema (if any) and
    confirm it's an action_button.
  - DO NOT use to call other agents' code — that's not what this is for.

Returns:
  - {status:"applied", result, request_id} where result is the execution
    outcome ({mode:"sync", result:{...}} or {mode:"async", job_id}).
  - {status:"pending", request_id, expires_at} — DO NOT retry.
  - {status:"denied", reason, rule_id, request_id}

Idempotency: highly recommended. Re-firing without a key may double-execute
if the first call's response was lost. Honor retry_after_ms.
"""

_DESC_APPEND_LOG = """\
Append a single entry to a log_stream module. Fast path: when you own the
module, the built-in rule auto-applies the append — typically returns
status="applied" in one round-trip.

When to use:
  - Streaming progress, events, or trace lines into a log_stream you own.
  - For bulk historical replay, prefer update_module to set the buffer
    wholesale rather than spamming append_log.

Returns:
  - {status:"applied", request_id, buffer_size, truncated_count?} on success.
  - {status:"pending" | "denied", ...} if a rule overrides the default.

Idempotency: pass a key per logical event. Auto-generated otherwise; rapid
retries with the same entry dedupe for ~60s. Honor retry_after_ms.
"""

_DESC_LIST_MY_MODULES = """\
List modules the calling agent owns. Use to discover module_ids before
calling get_module, update_module, or delete_module.

Args:
  - page_id (optional): filter to a single page.
  - type (optional): filter to a single module type.
  - limit (1-200, default 50), cursor (opaque, from prior response).

Returns: {items: [{id, type, title, page_id, position, data, config,
version, updated_at, ...}], next_cursor}. The agent should treat its own
cached view as STALE when next_cursor is set — paginate.

Errors: rate_limit, service_unavailable. Honor retry_after_ms.
"""

_DESC_GET_MODULE = """\
Fetch the full current state of one module by id. Use to:
  - Re-read version + data/config before calling update_module with
    expected_version (avoids optimistic-concurrency 409s).
  - Inspect action_button payload schemas before fire_action.
  - Diagnose a broken widget — the response includes health.render_ok and, if
    invalid, health.errors (per-field {section, loc, msg}) you can feed back
    into update_module.

You can read ANY live module (not only your own); the response includes
"owned" (bool) telling you whether you can edit it without admin approval.

Args: module_id.
Returns: the module object (list_my_modules shape) plus "owned" and "health".
Errors: not_found (module unknown/deleted), rate_limit.
"""

_DESC_LIST_PAGES = """\
List every dashboard page, so you can find a page_id to place a widget on
(propose_module) or pick a page to render/screenshot.

Args: limit (1-200, default 50), cursor.
Returns: {items: [{id, slug, name, type, owned, module_count,
my_module_count}], next_cursor}. "owned" means you can edit modules on it
without admin approval; "my_module_count" is how many modules there you own.

Errors: rate_limit, service_unavailable.
"""

_DESC_WHOAMI = """\
Return your own agent identity and capabilities: id, display_name, and the
permissions block the admin granted you. Call this once at the start of a
session to learn who you are and what you're allowed to do.

Args: none.
Returns: {agent: {id, display_name, permissions}}.
Errors: rate_limit, service_unavailable.
"""

_DESC_LIST_MODULE_SCHEMAS = """\
List the JSON Schema for EVERY module type at once — use this to discover what
widget types exist and their data/config shapes before building one. Prefer
get_module_schema(type) when you already know the single type you want.

Args: none.
Returns: {types: [...], items: [{type, data_schema, config_schema, ...}]}.
Every config schema includes appearance for per-widget theme/color.
Errors: rate_limit, service_unavailable.
"""

_DESC_VALIDATE_MODULE = """\
Dry-run: check whether a data/config payload is valid for a module type WITHOUT
writing anything. Call this to confirm a widget is well-formed before
propose_module/update_module, so you don't burn a write on an invalid payload.

Args: type, data (object), config (object).
Returns: {ok: bool, type_known: bool, errors: [{section:"data"|"config", loc,
msg, type}]}. When ok is false, fix the listed fields and re-validate.
Errors: rate_limit.
"""

_DESC_MODULE_HEALTH = """\
Report render health for the modules you own — i.e. which of your widgets would
fail to render and why. Use this as your "is anything broken?" check, then fix
each with update_module using the structured errors.

Args:
  - page_id (optional): limit to one page.
  - only_broken (default false): return just the broken modules.
  - limit (1-200, default 50), cursor (paginate).

Returns: {items: [{id, type, title, page_id, render_ok, errors:[{section, loc,
msg, type}], schema_version, version, updated_at}], next_cursor, checked}.
"checked" is how many modules were evaluated this page; if next_cursor is set,
keep paging (a page can be all-healthy yet more remain).
Errors: rate_limit, service_unavailable.
"""

_DESC_RENDER_PAGE = """\
Get a structured, headless view of what a page currently looks like: every
module (any owner) in display order, an ASCII grid sketch of the layout, and
which modules are broken. Use this to understand a dashboard's content and
arrangement without pixels. For an actual image, use screenshot_page.

Args: page_id.
Returns: {page:{id,name,slug,type}, modules:[{...module, health}],
layout:{columns, rows, ascii}, broken_module_ids, summary:{total, broken}}.
Errors: not_found (page), rate_limit, service_unavailable.
"""

_DESC_SCREENSHOT_PAGE = """\
Capture a real PNG screenshot of the live dashboard page as the admin sees it
(rendered in headless Chromium — includes charts, theming, and layout). Use
after editing widgets to visually confirm the result, or to inspect a page you
can't otherwise picture. For a fast, text-only view use render_page instead.

Args:
  - page_id.
  - viewport_width (optional, 360-3840; default 1280 → the 3-column layout).
  - full_page (default true): capture the whole scroll height, not just the fold.

Returns: an image (PNG) you can view directly.
Errors:
  - service_unavailable — the screenshot sidecar isn't configured/reachable
    (the admin must set PDASH_SCREENSHOT_SERVICE_URL); fall back to render_page.
  - not_found (page), rate_limit.
"""

_DESC_LIST_MY_PENDING_REQUESTS = """\
Reconciliation tool: when a write returned status="pending", call this to
see whether it's still pending, applied, denied, or expired. Also includes
recently-resolved requests (~last 24h).

Args:
  - status_filter (optional, csv): pending,approved,denied,applied,
    application_failed,superseded,expired. Default: pending.
  - limit (1-200, default 50), cursor.

Returns: {items: [{id, action_type, status, created_at, decided_at?,
decided_by?, expires_at, decision_reason?}], next_cursor}.

When status is "denied" or "applied", decision_reason carries the admin's
note (e.g. "put this on the ops page, not home" or "too noisy, batch these").
READ it before re-proposing — adjust your request to follow the guidance
rather than re-submitting an identical write that will be denied again.

DO NOT retry pending writes — wait for them to resolve here. Honor
retry_after_ms on rate_limit errors; don't poll faster than once a minute.
"""

_DESC_GET_MODULE_SCHEMA = """\
Get the JSON Schema for a module type's data + config payloads, plus
example payloads and the default permissions block.

Call BEFORE propose_module or update_module to avoid invalid_params.
Cache the result for the session.
Every config schema includes appearance for per-widget theme/color.

Args: type — one of: markdown, key_value, table, timeseries, log_stream,
link_list, iframe, action_button, notification, file.
Returns: {data_schema, config_schema, examples, permissions_default}.
Errors: not_found (unknown type), rate_limit.
"""

_DESC_GET_FILE_DROPBOX = """\
Discover WHERE to drop a file so it can be shown on the dashboard. You run on
the same host as pdash, so you write the file to a directory on disk (no upload)
and then call register_file to claim it.

Args: page_id (optional) — the dashboard you intend the file for.
Returns: {inbox_root, target?, pages:[{page_id, slug, name, drop_path}],
max_bytes, mime_allowlist, guidance}. Passing page_id creates+returns that
page's "target" drop dir; otherwise drop into a page's drop_path or inbox_root.

Workflow: get_file_dropbox(page_id) -> write your file into 'target' on disk ->
register_file(inbox_name=<bare filename>, page_id=<same>). The path is the path
the pdash backend sees; if your filesystem is mounted differently, map it.
Errors: not_found (page), rate_limit, service_unavailable.
"""

_DESC_REGISTER_FILE = """\
Claim a file you dropped into the inbox so pdash stores + serves it. Like every
agent write this goes through the approval engine: status is applied, pending,
or denied. To DISPLAY it, then call propose_module(type="file", data={file_id,
kind, display_name}) — get_module_schema("file") for the shape.

Args:
  - inbox_name: the bare filename you wrote (no slashes / "..").
  - display_name: human label shown in the UI.
  - page_id (optional): the dashboard the file is for (and which inbox subfolder
    it's in — pass the same page_id you used with get_file_dropbox).
  - purpose (optional), rationale (optional), idempotency_key (optional).

Returns: {status:"applied", file_id, url, file} | {status:"pending",
request_id, expires_at} | {status:"denied", reason, rule_id}.
DO NOT retry a pending result — poll list_my_pending_requests. If you change the
file's bytes before the admin approves, the apply fails (application_failed) —
re-drop and register again.
Errors: invalid_params (bad/traversing name, too large, mime not allowed),
not_found (file not in inbox, or page), rate_limit, service_unavailable.
"""

_DESC_LIST_MY_FILES = """\
List the files you've registered (so you can find a file_id to reference in a
file module).

Args: limit (1-200, default 50), cursor.
Returns: {items:[{id, display_name, kind, mime, size_bytes, page_id, url,
created_at, status}], next_cursor}.
Errors: rate_limit, service_unavailable.
"""


# -- ungated onboarding tools (no agent API key required) -------------------

_DESC_ONBOARDING = """\
START HERE if you have no pdash API key. Explains how to wire up your MCP client,
register, and unlock the full tool set. Requires NO key — callable by a brand-new
client.

When to use:
  - You have added this MCP server to your client's MCP configuration (no
    Authorization header yet) but don't yet have an hb_agt_ key. Every other tool
    returns auth_required until registration completes.

Args: none.
Returns: {service, auth_model, steps:[...], notes:[...]} — a plain-language
guide to MCP client setup -> request_registration -> admin approval ->
claim_registration -> update MCP config with your key.

This tool only reads guidance; it does not register you. Call
request_registration next (via MCP tools, not raw HTTP).
"""

_DESC_REQUEST_REGISTRATION = """\
Request to become a registered agent. Requires NO key. The request ALWAYS lands
pending for the pdash admin to approve in the web UI — it never grants access by
itself and never mints a key.

When to use:
  - Exactly once, when you have no hb_agt_ key. Pick a clear display_name for
    yourself; optionally add a description and a rationale the admin will read.

Args:
  - display_name (required, 1-80 chars): your name as it'll appear to the admin.
  - description (optional): what you are.
  - rationale (optional): why you want access (helps the admin decide).
  - client_hint (optional): where you're running (e.g. "Claude Code on host-x").

Returns: {status:"pending", registration_id, claim_token, expires_at,
next_step}. SAVE the claim_token — it is shown ONCE and is how you pick up your
key after approval.

Do NOT call this again to "retry"; that just creates a second pending request.
After the admin approves, poll claim_registration with your claim_token.

Errors:
  - conflict (agent.name_taken) — that display_name is taken; choose another.
  - rate_limit (registration.queue_full) — too many requests await approval; ask
    the admin to clear the queue, then retry later.
"""

_DESC_CLAIM_REGISTRATION = """\
Pick up the API key for a registration you requested. Requires NO key — you
authenticate with the claim_token from request_registration.

When to use:
  - After calling request_registration, poll this (~every 10s) until the admin
    approves. Do not retry request_registration in the meantime.

Args:
  - claim_token (required): the token from request_registration.
  - registration_id (optional): the id from request_registration (extra check).

Returns one of:
  - {status:"pending"} — not approved yet; poll again shortly.
  - {status:"approved", api_key, agent_id, display_name} — your key, shown ONCE.
    Save it, add it to your MCP client config as
    'Authorization: Bearer <api_key>' in headers, and reconnect.
  - {status:"denied", reason} — the admin declined; you may register again.
  - {status:"expired"} — the request expired before approval; register again.
  - {status:"claimed"} — already picked up (the key is shown only once).

Errors:
  - not_found (registration.not_found) — unknown/incorrect claim_token.
"""


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP) -> None:
    """Attach every MCP tool to the given FastMCP instance."""

    # -------------------- propose_module --------------------
    @mcp.tool(name="propose_module", description=_DESC_PROPOSE_MODULE)
    async def propose_module(
        page_id: str,
        type: str,
        title: str | None = None,
        data: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        permissions: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        rationale: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ProposeModuleArgs(
            page_id=page_id,
            type=type,
            title=title,
            data=data or {},
            config=config or {},
            permissions=permissions,
            idempotency_key=idempotency_key,
            rationale=rationale,
        )
        key = await _acquire_idem_key(agent.agent_id, "propose_module", args)
        body: dict[str, Any] = {
            "type": args.type,
            "page_id": args.page_id,
            "data": args.data,
            "config": args.config,
        }
        if args.title is not None:
            body["title"] = args.title
        if args.permissions is not None:
            body["permissions"] = args.permissions
        if args.rationale is not None:
            body["rationale"] = args.rationale
        return await _submit_write(
            agent.agent_id,
            "create_module",
            get_client().propose_module(agent.agent_id, idempotency_key=key, body=body),
        )

    # -------------------- update_module --------------------
    @mcp.tool(name="update_module", description=_DESC_UPDATE_MODULE)
    async def update_module(
        module_id: str,
        data: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        title: str | None = None,
        position: int | None = None,
        expected_version: int | None = None,
        idempotency_key: str | None = None,
        rationale: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = UpdateModuleArgs(
            module_id=module_id,
            data=data,
            config=config,
            title=title,
            position=position,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            rationale=rationale,
        )
        key = await _acquire_idem_key(agent.agent_id, "update_module", args)
        patch: dict[str, Any] = {}
        if args.data is not None:
            patch["data"] = args.data
        if args.config is not None:
            patch["config"] = args.config
        if args.title is not None:
            patch["title"] = args.title
        if args.position is not None:
            patch["position"] = args.position
        if not patch:
            raise _mcp_error(
                _INVALID_PARAMS,
                "update_module requires at least one of data/config/title/position",
            )
        body: dict[str, Any] = {"id": args.module_id, "patch": patch}
        if args.rationale is not None:
            body["rationale"] = args.rationale
        if args.expected_version is not None:
            body["expected_etag"] = f'W/"{args.expected_version}"'
        return await _submit_write(
            agent.agent_id,
            "update_module",
            get_client().update_module(agent.agent_id, idempotency_key=key, body=body),
        )

    # -------------------- delete_module --------------------
    @mcp.tool(name="delete_module", description=_DESC_DELETE_MODULE)
    async def delete_module(
        module_id: str,
        expected_version: int | None = None,
        idempotency_key: str | None = None,
        reason: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = DeleteModuleArgs(
            module_id=module_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            reason=reason,
        )
        key = await _acquire_idem_key(agent.agent_id, "delete_module", args)
        body: dict[str, Any] = {"id": args.module_id}
        if args.reason is not None:
            body["rationale"] = args.reason
        if args.expected_version is not None:
            body["expected_etag"] = f'W/"{args.expected_version}"'
        return await _submit_write(
            agent.agent_id,
            "delete_module",
            get_client().delete_module(agent.agent_id, idempotency_key=key, body=body),
        )

    # -------------------- propose_page --------------------
    @mcp.tool(name="propose_page", description=_DESC_PROPOSE_PAGE)
    async def propose_page(
        name: str,
        slug: str | None = None,
        description: str | None = None,
        type: Literal["agent", "canvas"] = "agent",
        idempotency_key: str | None = None,
        rationale: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ProposePageArgs(
            name=name,
            slug=slug,
            description=description,
            type=type,
            idempotency_key=idempotency_key,
            rationale=rationale,
        )
        key = await _acquire_idem_key(agent.agent_id, "propose_page", args)
        body: dict[str, Any] = {"name": args.name, "type": args.type}
        if args.slug is not None:
            body["slug"] = args.slug
        if args.description is not None:
            body["description"] = args.description
        if args.rationale is not None:
            body["rationale"] = args.rationale
        status, raw = await _call_backend(
            get_client().propose_page(agent.agent_id, idempotency_key=key, body=body)
        )
        return _status_envelope(status, raw)

    # -------------------- fire_action --------------------
    @mcp.tool(name="fire_action", description=_DESC_FIRE_ACTION)
    async def fire_action(
        module_id: str,
        target_id: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        rationale: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = FireActionArgs(
            module_id=module_id,
            target_id=target_id,
            payload=payload,
            idempotency_key=idempotency_key,
            rationale=rationale,
        )
        key = await _acquire_idem_key(agent.agent_id, "fire_action", args)
        # The backend currently accepts target_id directly. If we were given
        # only a module_id, resolve via get_module to extract the
        # action_target_id from the module's data.
        resolved_target = args.target_id
        if resolved_target is None:
            mod = await _call_backend(get_client().get_module(agent.agent_id, args.module_id))
            if mod.get("type") != "action_button":
                raise _mcp_error(
                    _INVALID_PARAMS,
                    f"module {args.module_id} is type {mod.get('type')}, not action_button",
                )
            resolved_target = (mod.get("data") or {}).get("action_target_id")
            if not resolved_target:
                raise _mcp_error(
                    _INVALID_PARAMS,
                    f"module {args.module_id} has no action_target_id in data",
                )
        body: dict[str, Any] = {"target_id": resolved_target}
        if args.payload is not None:
            body["payload"] = args.payload
        if args.rationale is not None:
            body["rationale"] = args.rationale
        status, raw = await _call_backend(
            get_client().fire_action(agent.agent_id, idempotency_key=key, body=body)
        )
        return _status_envelope(status, raw)

    # -------------------- append_log --------------------
    @mcp.tool(name="append_log", description=_DESC_APPEND_LOG)
    async def append_log(
        module_id: str,
        entry: dict[str, Any],
        idempotency_key: str | None = None,
        rationale: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = AppendLogArgs(
            module_id=module_id,
            entry=LogEntry(**entry),
            idempotency_key=idempotency_key,
            rationale=rationale,
        )
        key = await _acquire_idem_key(agent.agent_id, "append_log", args)
        body: dict[str, Any] = {
            "module_id": args.module_id,
            "lines": [args.entry.model_dump(exclude_none=True)],
        }
        if args.rationale is not None:
            body["rationale"] = args.rationale
        status, raw = await _call_backend(
            get_client().append_log(agent.agent_id, idempotency_key=key, body=body)
        )
        return _status_envelope(status, raw)

    # -------------------- list_my_modules --------------------
    @mcp.tool(name="list_my_modules", description=_DESC_LIST_MY_MODULES)
    async def list_my_modules(
        page_id: str | None = None,
        type: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ListMyModulesArgs(page_id=page_id, type=type, limit=limit, cursor=cursor)
        body = await _call_backend(
            get_client().list_my_modules(
                agent.agent_id,
                page_id=args.page_id,
                cursor=args.cursor,
                limit=args.limit,
            )
        )
        items = body.get("items", [])
        if args.type is not None:
            items = [module for module in items if module.get("type") == args.type]
        # Report items as "fresh" while the SSE consumer is connected, else
        # "unknown" (the live bus is our only freshness signal for now).
        staleness = "fresh" if decision_cache.is_connected() else "unknown"
        for module in items:
            module.setdefault("staleness", staleness)
        return {"items": items, "next_cursor": body.get("next_cursor")}

    # -------------------- get_module --------------------
    @mcp.tool(name="get_module", description=_DESC_GET_MODULE)
    async def get_module(
        module_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = GetModuleArgs(module_id=module_id)
        mod = await _call_backend(get_client().get_module(agent.agent_id, args.module_id))
        mod.setdefault(
            "staleness", "fresh" if decision_cache.is_connected() else "unknown"
        )
        return mod

    # -------------------- list_pages --------------------
    @mcp.tool(name="list_pages", description=_DESC_LIST_PAGES)
    async def list_pages(
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ListPagesArgs(limit=limit, cursor=cursor)
        return await _call_backend(
            get_client().list_pages(agent.agent_id, cursor=args.cursor, limit=args.limit)
        )

    # -------------------- list_my_pending_requests --------------------
    @mcp.tool(name="list_my_pending_requests", description=_DESC_LIST_MY_PENDING_REQUESTS)
    async def list_my_pending_requests(
        status_filter: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ListMyPendingRequestsArgs(status_filter=status_filter, limit=limit, cursor=cursor)
        return await _call_backend(
            get_client().list_my_pending_requests(
                agent.agent_id,
                status_filter=args.status_filter,
                cursor=args.cursor,
                limit=args.limit,
            )
        )

    # -------------------- get_module_schema --------------------
    @mcp.tool(name="get_module_schema", description=_DESC_GET_MODULE_SCHEMA)
    async def get_module_schema(
        type: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = GetModuleSchemaArgs(type=type)
        return await _call_backend(get_client().module_schema(agent.agent_id, args.type))

    # -------------------- whoami --------------------
    @mcp.tool(name="whoami", description=_DESC_WHOAMI)
    async def whoami(ctx: Context | None = None) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        return await _call_backend(get_client().whoami(agent.agent_id))

    # -------------------- list_module_schemas --------------------
    @mcp.tool(name="list_module_schemas", description=_DESC_LIST_MODULE_SCHEMAS)
    async def list_module_schemas(ctx: Context | None = None) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        return await _call_backend(get_client().list_module_schemas(agent.agent_id))

    # -------------------- validate_module --------------------
    @mcp.tool(name="validate_module", description=_DESC_VALIDATE_MODULE)
    async def validate_module(
        type: str,
        data: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ValidateModuleArgs(type=type, data=data or {}, config=config or {})
        body = {"type": args.type, "data": args.data, "config": args.config}
        return await _call_backend(get_client().validate_module(agent.agent_id, body=body))

    # -------------------- module_health --------------------
    @mcp.tool(name="module_health", description=_DESC_MODULE_HEALTH)
    async def module_health(
        page_id: str | None = None,
        only_broken: bool = False,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ModuleHealthArgs(
            page_id=page_id, only_broken=only_broken, limit=limit, cursor=cursor
        )
        return await _call_backend(
            get_client().module_health(
                agent.agent_id,
                page_id=args.page_id,
                only_broken=args.only_broken,
                cursor=args.cursor,
                limit=args.limit,
            )
        )

    # -------------------- render_page --------------------
    @mcp.tool(name="render_page", description=_DESC_RENDER_PAGE)
    async def render_page(
        page_id: str,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = RenderPageArgs(page_id=page_id)
        return await _call_backend(get_client().render_page(agent.agent_id, args.page_id))

    # -------------------- screenshot_page --------------------
    @mcp.tool(name="screenshot_page", description=_DESC_SCREENSHOT_PAGE)
    async def screenshot_page(
        page_id: str,
        viewport_width: int | None = None,
        full_page: bool = True,
        ctx: Context | None = None,
    ) -> Image:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ScreenshotPageArgs(
            page_id=page_id, viewport_width=viewport_width, full_page=full_page
        )
        data, content_type = await _call_backend(
            get_client().page_screenshot(
                agent.agent_id,
                args.page_id,
                viewport_width=args.viewport_width,
                full_page=args.full_page,
            )
        )
        fmt = "png"
        if "/" in content_type:
            subtype = content_type.split("/", 1)[1].split(";")[0].strip()
            if subtype:
                fmt = subtype
        return Image(data=data, format=fmt)

    # -------------------- get_file_dropbox --------------------
    @mcp.tool(name="get_file_dropbox", description=_DESC_GET_FILE_DROPBOX)
    async def get_file_dropbox(
        page_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = GetFileDropboxArgs(page_id=page_id)
        return await _call_backend(
            get_client().file_dropbox(agent.agent_id, page_id=args.page_id)
        )

    # -------------------- register_file --------------------
    @mcp.tool(name="register_file", description=_DESC_REGISTER_FILE)
    async def register_file(
        inbox_name: str,
        display_name: str,
        page_id: str | None = None,
        purpose: str | None = None,
        idempotency_key: str | None = None,
        rationale: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = RegisterFileArgs(
            inbox_name=inbox_name,
            display_name=display_name,
            page_id=page_id,
            purpose=purpose,
            idempotency_key=idempotency_key,
            rationale=rationale,
        )
        key = await _acquire_idem_key(agent.agent_id, "register_file", args)
        body: dict[str, Any] = {
            "inbox_name": args.inbox_name,
            "display_name": args.display_name,
        }
        if args.page_id is not None:
            body["page_id"] = args.page_id
        if args.purpose is not None:
            body["purpose"] = args.purpose
        if args.rationale is not None:
            body["rationale"] = args.rationale
        return await _submit_write(
            agent.agent_id,
            "register_file",
            get_client().register_file(agent.agent_id, idempotency_key=key, body=body),
        )

    # -------------------- list_my_files --------------------
    @mcp.tool(name="list_my_files", description=_DESC_LIST_MY_FILES)
    async def list_my_files(
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        assert ctx is not None
        agent = await _require_agent(ctx)
        args = ListMyFilesArgs(limit=limit, cursor=cursor)
        return await _call_backend(
            get_client().my_files(agent.agent_id, cursor=args.cursor, limit=args.limit)
        )

    # ====================================================================
    # Ungated onboarding tools (NO agent key required). These deliberately
    # skip _require_agent so a brand-new client can connect and register.
    # ====================================================================

    # -------------------- onboarding --------------------
    @mcp.tool(name="onboarding", description=_DESC_ONBOARDING)
    async def onboarding() -> dict[str, Any]:
        return onboarding_payload()

    # -------------------- request_registration --------------------
    @mcp.tool(name="request_registration", description=_DESC_REQUEST_REGISTRATION)
    async def request_registration(
        display_name: str,
        description: str | None = None,
        rationale: str | None = None,
        client_hint: str | None = None,
    ) -> dict[str, Any]:
        args = RequestRegistrationArgs(
            display_name=display_name,
            description=description,
            rationale=rationale,
            client_hint=client_hint,
        )
        body: dict[str, Any] = {"display_name": args.display_name}
        if args.description is not None:
            body["description"] = args.description
        if args.rationale is not None:
            body["rationale"] = args.rationale
        if args.client_hint is not None:
            body["client_hint"] = args.client_hint
        out = await _call_backend(get_client().register_agent(body=body))
        return {
            "status": out.get("status", "pending"),
            "registration_id": out.get("registration_id"),
            "claim_token": out.get("claim_token"),
            "expires_at": out.get("expires_at"),
            "next_step": (
                "Save claim_token (shown once). The pdash admin must approve this request, then "
                "call claim_registration(claim_token=...) — poll about every 10s. Do NOT call "
                "request_registration again."
            ),
        }

    # -------------------- claim_registration --------------------
    @mcp.tool(name="claim_registration", description=_DESC_CLAIM_REGISTRATION)
    async def claim_registration(
        claim_token: str,
        registration_id: str | None = None,
    ) -> dict[str, Any]:
        args = ClaimRegistrationArgs(claim_token=claim_token, registration_id=registration_id)
        body: dict[str, Any] = {"claim_token": args.claim_token}
        if args.registration_id is not None:
            body["registration_id"] = args.registration_id
        out = await _call_backend(get_client().claim_registration(body=body))
        status = out.get("status")
        if status == "approved":
            out["next_step"] = (
                "Approved. Save api_key (shown ONCE), add it to your MCP client config as "
                "'Authorization: Bearer <api_key>' in headers, and reconnect. You can now use the "
                "full tool set; every write goes through the approval engine."
            )
        elif status == "pending":
            out["next_step"] = (
                "Still pending admin approval. Poll again in ~10s; do not re-register."
            )
        elif status == "denied":
            out["next_step"] = (
                "The admin denied this request. Read 'reason'; you may register again with changes."
            )
        elif status == "expired":
            out["next_step"] = "This registration expired before approval. Call request_registration again."
        return out


__all__ = ["register_tools"]
