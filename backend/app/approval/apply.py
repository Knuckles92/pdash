"""Apply an approved request to the live data model.

Every entry point is called *inside the same transaction* that flipped the
request status from pending->approved (or auto_approve). The lifecycle
transition to ``applied`` happens here, followed by an ``activity_log`` write
in the calling router. Failures raise :class:`ApplyError`; callers translate
those into a ``mark_application_failed`` call.

Action-type dispatch table (PLAN §7.5 sub-state for fire_action):

    create_module          -> :func:`apply_create_module`
    update_module_data     -> :func:`apply_update_module`
    update_module_config   -> :func:`apply_update_module`
    update_module_meta     -> :func:`apply_update_module`
    delete_module          -> :func:`apply_delete_module`
    create_page            -> :func:`apply_create_page`
    delete_page            -> :func:`apply_delete_page`
    fire_action_button     -> :func:`apply_fire_action`
    append_log             -> :func:`apply_append_log` (special path,
                              invoked directly from the route since it is
                              never persisted as a pending request — see
                              the route handler).

**Provisional module IDs.** When an agent calls ``propose_module`` and the
engine routes it to ``pending``, we mint the ULID *up front* and stash it in
``proposed_payload.provisional_id``. If/when the admin later approves the
request, the apply function reuses that same ID as the real module's
primary key. This way, agents that cached the provisional id from the
202 response continue to work after approval. (Documented in
PLAN.md open questions; the value is also returned by the propose endpoint.)
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from .. import modules as module_registry
from ..auth.secrets import get_kv
from ..config import get_settings
from ..errors import ProblemDetail
from ..events.publish import publish_after_commit
from ..ids import new_id
from ..models import (
    ActionTarget,
    AgentMessage,
    AgentRegistrationRequest,
    ApprovalRequest,
    Module,
    Page,
    utcnow_iso,
)
from ..services.agent_registration import approve_registration_row
from ..services.files import (
    FilePathError,
    file_summary,
    persist_registered_file,
    resolve_inbox_file,
    stat_and_sha256,
)
from . import lifecycle


def _module_summary(row: Module) -> dict[str, Any]:
    """Slim representation suitable for inlining in events."""
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "page_id": row.page_id,
        "position": row.position,
        "version": row.version,
        "updated_at": row.updated_at,
        "owner_kind": row.owner_kind,
        "owner_id": row.owner_id,
    }


def _page_summary(row: Page) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "kind": row.kind,
        "owner_kind": row.owner_kind,
        "owner_id": row.owner_id,
        "deleted_at": row.deleted_at,
    }


# Pattern for resolving secret references stored in kv_settings.
# Example: `action_target_secret:<target_id>:bearer`.
SECRET_KV_PREFIX = "action_target_secret"


def secret_kv_key(target_id: str, field: str) -> str:
    return f"{SECRET_KV_PREFIX}:{target_id}:{field}"


class ApplyError(Exception):
    """Raised when the underlying mutation could not be applied."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class ApplyResult:
    """Returned by :func:`apply_request` to the caller."""

    target_kind: str | None
    target_id: str | None
    extra: dict[str, Any]


def _load_payload(request: ApprovalRequest) -> dict[str, Any]:
    return json.loads(request.proposed_payload)


def _agent_actor_for(request: ApprovalRequest) -> str:
    return f"agent:{request.agent_id}"


# ---------------------------------------------------------------------------
# create_module
# ---------------------------------------------------------------------------


async def apply_create_module(
    session: AsyncSession, request: ApprovalRequest
) -> ApplyResult:
    payload = _load_payload(request)
    page_id = payload["page_id"]
    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is not None:
        raise ApplyError("page.not_found", f"page {page_id} not found")

    # Re-validate at apply time.
    mtype = payload["type"]
    try:
        clean_data = module_registry.validate_data(mtype, payload.get("data", {}))
        clean_config = module_registry.validate_config(mtype, payload.get("config", {}))
    except KeyError as exc:
        raise ApplyError("module.unknown_type", str(exc)) from exc
    except Exception as exc:
        raise ApplyError("module.invalid_payload", str(exc)) from exc

    # Reuse the provisional id baked into the payload.
    mod_id = payload.get("provisional_id") or new_id("mod")
    now = utcnow_iso()
    row = Module(
        id=mod_id,
        type=mtype,
        title=payload.get("title"),
        owner_kind="agent",
        owner_id=request.agent_id,
        page_id=page_id,
        position=payload.get("position", 0),
        grid=json.dumps(payload["grid"]) if payload.get("grid") else None,
        permissions=json.dumps(payload.get("permissions", {})),
        data=json.dumps(clean_data),
        config=json.dumps(clean_config),
        schema_version=1,
        version=1,
        created_at=now,
        updated_at=now,
        last_updated_by=_agent_actor_for(request),
    )
    session.add(row)
    await session.flush()

    # Update the request's target_id if it was not set (always the case for
    # create_module — the target didn't exist when the request was created).
    request.target_kind = "module"
    request.target_id = mod_id

    # Phase 5: notify subscribers.
    summary = _module_summary(row)
    publish_after_commit(session, f"page:{page_id}", "module_added", {"module": summary})
    publish_after_commit(session, f"module:{mod_id}", "module_added", {"module": summary})

    return ApplyResult(target_kind="module", target_id=mod_id, extra={"module_id": mod_id})


# ---------------------------------------------------------------------------
# update_module_*
# ---------------------------------------------------------------------------


async def apply_update_module(
    session: AsyncSession, request: ApprovalRequest
) -> ApplyResult:
    payload = _load_payload(request)
    mod_id = payload["id"]
    row = await session.get(Module, mod_id)
    if row is None or row.deleted_at is not None:
        raise ApplyError("module.not_found", f"module {mod_id} not found")

    patch: dict[str, Any] = payload.get("patch", {})
    new_data = json.loads(row.data) if "data" not in patch else patch["data"]
    new_config = json.loads(row.config) if "config" not in patch else patch["config"]
    if "data" in patch or "config" in patch:
        try:
            new_data = module_registry.validate_data(row.type, new_data)
            new_config = module_registry.validate_config(row.type, new_config)
        except Exception as exc:
            raise ApplyError("module.invalid_payload", str(exc)) from exc

    if "title" in patch:
        row.title = patch["title"]
    if "position" in patch:
        row.position = patch["position"]
    if "data" in patch:
        row.data = json.dumps(new_data)
    if "config" in patch:
        row.config = json.dumps(new_config)
    if "page_id" in patch and patch["page_id"]:
        target_page = await session.get(Page, patch["page_id"])
        if target_page is None or target_page.deleted_at is not None:
            raise ApplyError("page.not_found", f"page {patch['page_id']} not found")
        row.page_id = patch["page_id"]

    row.version += 1
    row.updated_at = utcnow_iso()
    row.last_updated_by = _agent_actor_for(request)
    await session.flush()

    summary = _module_summary(row)
    publish_after_commit(session, f"page:{row.page_id}", "module_updated", {"module": summary})
    publish_after_commit(session, f"module:{mod_id}", "module_updated", {"module": summary})

    return ApplyResult(target_kind="module", target_id=mod_id, extra={"version": row.version})


# ---------------------------------------------------------------------------
# delete_module
# ---------------------------------------------------------------------------


async def apply_delete_module(
    session: AsyncSession, request: ApprovalRequest
) -> ApplyResult:
    payload = _load_payload(request)
    mod_id = payload["id"]
    row = await session.get(Module, mod_id)
    if row is None or row.deleted_at is not None:
        raise ApplyError("module.not_found", f"module {mod_id} not found")
    now = utcnow_iso()
    row.deleted_at = now
    row.updated_at = now
    row.version += 1
    row.last_updated_by = _agent_actor_for(request)
    await session.flush()

    publish_after_commit(
        session, f"page:{row.page_id}", "module_removed", {"module_id": mod_id}
    )
    publish_after_commit(
        session, f"module:{mod_id}", "module_removed", {"module_id": mod_id}
    )
    return ApplyResult(target_kind="module", target_id=mod_id, extra={"deleted": True})


# ---------------------------------------------------------------------------
# create_page
# ---------------------------------------------------------------------------


async def apply_create_page(
    session: AsyncSession, request: ApprovalRequest
) -> ApplyResult:
    payload = _load_payload(request)
    pid = payload.get("provisional_id") or new_id("pg")
    row = Page(
        id=pid,
        slug=payload["slug"],
        name=payload["name"],
        description=payload.get("description"),
        kind=payload.get("kind", "custom"),
        owner_kind="agent",
        owner_id=request.agent_id,
        created_at=utcnow_iso(),
    )
    session.add(row)
    await session.flush()
    request.target_kind = "page"
    request.target_id = pid
    publish_after_commit(session, "pages", "page_added", {"page": _page_summary(row)})
    return ApplyResult(target_kind="page", target_id=pid, extra={"page_id": pid})


# ---------------------------------------------------------------------------
# delete_page
# ---------------------------------------------------------------------------


async def apply_delete_page(
    session: AsyncSession, request: ApprovalRequest
) -> ApplyResult:
    payload = _load_payload(request)
    pid = payload["id"]
    row = await session.get(Page, pid)
    if row is None or row.deleted_at is not None:
        raise ApplyError("page.not_found", f"page {pid} not found")
    if row.kind == "home":
        raise ApplyError("page.cannot_delete_home", "home page cannot be deleted")
    row.deleted_at = utcnow_iso()
    # `cascade=true` is a hint for the FK — modules.page_id has ON DELETE
    # CASCADE, but we soft-delete here so the modules remain visible until the
    # admin sweep. If the payload sets cascade=true we also soft-delete each
    # child module.
    if payload.get("cascade"):
        from sqlalchemy import select  # local import to avoid top-level cost
        mods = (
            await session.execute(
                select(Module).where(Module.page_id == pid, Module.deleted_at.is_(None))
            )
        ).scalars().all()
        for mod in mods:
            mod.deleted_at = utcnow_iso()
            mod.version += 1
    await session.flush()
    publish_after_commit(session, "pages", "page_removed", {"page_id": pid})
    return ApplyResult(target_kind="page", target_id=pid, extra={"deleted": True})


# ---------------------------------------------------------------------------
# fire_action_button
# ---------------------------------------------------------------------------


async def _execute_webhook(target: ActionTarget, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = json.loads(target.config or "{}")
    url = cfg.get("url")
    if not url:
        return {"ok": False, "error": "webhook target missing url"}
    method = cfg.get("method", "POST").upper()
    headers = dict(cfg.get("headers") or {})
    body = payload or cfg.get("default_payload") or {}
    timeout = float(cfg.get("timeout_seconds", 30))
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, json=body, headers=headers)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            preview = resp.text[:4096]
            return {
                "ok": 200 <= resp.status_code < 400,
                "status_code": resp.status_code,
                "body_preview": preview,
                "elapsed_ms": elapsed_ms,
            }
    except Exception as exc:  # noqa: BLE001 — webhook errors are user-visible
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {"ok": False, "error": str(exc), "elapsed_ms": elapsed_ms}


async def _resolve_auth_header(
    session: AsyncSession, target_id: str, auth_cfg: dict[str, Any] | None
) -> dict[str, str]:
    """Translate an ``auth`` block into HTTP headers.

    ``auth`` shape::

        {"kind": "bearer", "secret_ref": "main"}  # reads action_target_secret:<id>:main

    Plaintext secrets are *never* stored on ``action_targets.config``; instead
    the config references a ``kv_settings`` row by name. This keeps
    redacted reads cheap and avoids accidentally leaking secrets in audit
    payloads. ``secret_ref`` may be omitted, in which case we look up the
    canonical ``<id>:bearer`` row.
    """
    if not auth_cfg:
        return {}
    kind = (auth_cfg.get("kind") or "").lower()
    if kind == "bearer":
        ref = auth_cfg.get("secret_ref") or "bearer"
        secret = await get_kv(session, secret_kv_key(target_id, ref))
        if not secret:
            return {}
        return {"Authorization": f"Bearer {secret}"}
    if kind == "header":
        # Generic shape: {"kind":"header","name":"X-Foo","secret_ref":"foo"}.
        name = auth_cfg.get("name")
        ref = auth_cfg.get("secret_ref") or "header"
        if not name:
            return {}
        secret = await get_kv(session, secret_kv_key(target_id, ref))
        if not secret:
            return {}
        return {name: secret}
    return {}


async def _execute_mcp_tool(
    session: AsyncSession, target: ActionTarget, payload: dict[str, Any]
) -> dict[str, Any]:
    """Invoke a tool on a *remote* MCP server.

    Uses the official ``mcp`` Python SDK as a streamable HTTP client. We don't
    keep a persistent session per target — the tool surface here is
    "fire-and-forget" admin actions, latency budget is generous, and one-shot
    sessions keep the code simple. If we later need long-lived sessions we
    can pool them here.

    Config shape::

        {
            "url": "https://ha.lan/mcp",
            "tool_name": "homeassistant.toggle",
            "auth": {"kind":"bearer","secret_ref":"main"}
        }
    """
    cfg = json.loads(target.config or "{}")
    url = cfg.get("url")
    tool_name = cfg.get("tool_name")
    if not url:
        return {"ok": False, "error": "mcp_tool target missing url"}
    if not tool_name:
        return {"ok": False, "error": "mcp_tool target missing tool_name"}
    timeout = float(cfg.get("timeout_seconds", 30))
    auth_headers = await _resolve_auth_header(session, target.id, cfg.get("auth"))
    started = time.monotonic()
    try:
        # Importing lazily so test environments without the mcp SDK can still
        # exercise the dispatcher branch via mocking.
        from datetime import timedelta

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(
            url,
            headers=auth_headers or None,
            timeout=timedelta(seconds=timeout),
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as mcp_session:
                await mcp_session.initialize()
                tool_result = await mcp_session.call_tool(
                    tool_name, arguments=payload or {}
                )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        # CallToolResult exposes `.isError` and `.content` (list of content blocks).
        is_error = bool(getattr(tool_result, "isError", False))
        # Convert content blocks into a serializable preview.
        content_preview: list[dict[str, Any]] = []
        for block in getattr(tool_result, "content", []) or []:
            try:
                if hasattr(block, "model_dump"):
                    content_preview.append(block.model_dump())
                else:
                    content_preview.append({"text": str(block)})
            except Exception:  # noqa: BLE001
                content_preview.append({"text": repr(block)})
        return {
            "ok": not is_error,
            "tool_name": tool_name,
            "content": content_preview[:8],
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "error": str(exc),
            "error_kind": type(exc).__name__,
            "elapsed_ms": elapsed_ms,
        }


async def _execute_agent_message(
    session: AsyncSession,
    target: ActionTarget,
    payload: dict[str, Any],
    *,
    from_actor: str,
) -> dict[str, Any]:
    """Drop a row in ``agent_messages`` for the target agent.

    The MCP tool surface for *reading* these messages is deferred — see
    PLAN.md and the TODO Phase 1.5 marker below.
    """
    cfg = json.loads(target.config or "{}")
    to_agent_id = cfg.get("to_agent_id")
    if not to_agent_id:
        return {"ok": False, "error": "agent_message target missing to_agent_id"}
    msg_id = new_id("msg")
    row = AgentMessage(
        id=msg_id,
        from_actor=from_actor,
        to_agent_id=to_agent_id,
        payload=json.dumps(payload or {}, separators=(",", ":"), default=str),
        created_at=utcnow_iso(),
    )
    session.add(row)
    try:
        await session.flush()
    except Exception as exc:  # noqa: BLE001 — FK violations land here.
        return {"ok": False, "error": str(exc)}
    # TODO Phase 1.5 / v1.5: expose a `read_messages` MCP tool so the target
    # agent can drain its inbox without going through the admin UI.
    return {"ok": True, "message_id": msg_id, "to_agent_id": to_agent_id}


async def _execute_local_script(
    target: ActionTarget, payload: dict[str, Any]
) -> dict[str, Any]:
    cfg = json.loads(target.config or "{}")
    cmd = cfg.get("command")
    if not cmd:
        return {"ok": False, "error": "local_script target missing command"}
    timeout = float(cfg.get("timeout_seconds", 30))
    args = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
    env_in = dict(cfg.get("env") or {})
    stdin = json.dumps(payload or {}, separators=(",", ":"))
    started = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **env_in},
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(stdin.encode("utf-8")), timeout=timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return {"ok": False, "error": "timeout", "elapsed_ms": elapsed_ms}
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout_preview": stdout_b.decode("utf-8", "replace")[:4096],
            "stderr_preview": stderr_b.decode("utf-8", "replace")[:4096],
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {"ok": False, "error": str(exc), "elapsed_ms": elapsed_ms}


async def dispatch_target(
    session: AsyncSession,
    target: ActionTarget,
    body_payload: dict[str, Any],
    *,
    from_actor: str,
) -> dict[str, Any]:
    """Dispatch by ``target.kind``. Returned dict always has ``ok`` set.

    Exposed so the admin ``POST /modules/{id}/fire`` endpoint can reuse the
    same execution paths without the approval-engine wrapper. Both paths
    serialize the same ``{ok, ...}`` shape into ``last_result``.
    """
    if target.kind == "webhook":
        return await _execute_webhook(target, body_payload)
    if target.kind == "local_script":
        return await _execute_local_script(target, body_payload)
    if target.kind == "mcp_tool":
        return await _execute_mcp_tool(session, target, body_payload)
    if target.kind == "agent_message":
        return await _execute_agent_message(
            session, target, body_payload, from_actor=from_actor
        )
    return {"ok": False, "error": f"unknown target kind {target.kind!r}"}


# In-process async job registry. Phase 4 only — durability lands later.
# TODO v1.5: replace with a persistent job store (SQLite-backed) so jobs
# survive process restarts. For now an `async_mode` target spawns a task
# that writes back the execution_result and executed_at on completion.
# (Out of Phase 6 scope: action-target async jobs are infrequent and the
# admin can simply re-fire from the UI if the process restarts mid-flight.)
_ASYNC_JOBS: dict[str, asyncio.Task[Any]] = {}


async def _fire_action_async(
    session: AsyncSession,
    request: ApprovalRequest,
    target: ActionTarget,
    *,
    target_id: str,
    body_payload: dict[str, Any],
    from_actor: str,
) -> ApplyResult:
    """Async-mode fire_action: queue a background task and return immediately.

    Marks the request as executed=true (queued) with a ``job_id`` stub; a
    background task writes the real result back onto the row once it resolves.
    """
    job_id = new_id("job")
    result_stub = {
        "ok": True,
        "mode": "async",
        "job_id": job_id,
        "queued_at": utcnow_iso(),
    }
    # Lifecycle: still mark executed=true (queued). The real result lands
    # on a follow-up write to the row.
    lifecycle.mark_executed(request, result=result_stub)
    # Capture identifiers; do not capture `target` (different session).
    captured_target_id = target.id
    captured_request_id = request.id

    async def _run() -> None:
        from ..db import get_sessionmaker  # local import to avoid cycle
        sm = get_sessionmaker()
        async with sm() as bg_session:
            from sqlalchemy import text as sql_text
            await bg_session.execute(sql_text("BEGIN IMMEDIATE"))
            bg_target = await bg_session.get(ActionTarget, captured_target_id)
            if bg_target is None:
                await bg_session.rollback()
                return
            final = await dispatch_target(
                bg_session, bg_target, body_payload, from_actor=from_actor
            )
            bg_apr = await bg_session.get(ApprovalRequest, captured_request_id)
            if bg_apr is not None:
                bg_apr.executed_at = utcnow_iso()
                bg_apr.execution_result = json.dumps(final)
            await bg_session.commit()

    task = asyncio.create_task(_run())
    _ASYNC_JOBS[job_id] = task
    # Default-arg `jid=job_id` binds the current job_id at registration time so
    # the callback pops the right entry even after the loop variable moves on.
    task.add_done_callback(lambda _t, jid=job_id: _ASYNC_JOBS.pop(jid, None))

    return ApplyResult(
        target_kind="action_target",
        target_id=target_id,
        extra={"execution_result": result_stub, "job_id": job_id},
    )


async def apply_fire_action(
    session: AsyncSession, request: ApprovalRequest
) -> ApplyResult:
    """Apply an approved fire_action_button request.

    Marks the request as ``applied`` (via the lifecycle helper), then attempts
    execution against the resolved action target. Execution success/failure
    populates ``executed_at`` and ``execution_result``. The request status
    itself stays ``applied`` per PLAN §7.5 — the ``execution_result.ok``
    field is the bit the UI should branch on.

    Async mode: the function returns immediately with a ``job_id`` in
    ``execution_result.job_id``; a background task writes the real result
    onto a fresh ``approval_requests`` row read once it resolves.
    """
    payload = _load_payload(request)
    target_id = payload["target_id"]
    target = await session.get(ActionTarget, target_id)
    if target is None or target.deleted_at is not None:
        raise ApplyError("action_target.not_found", f"target {target_id} not found")
    if not target.enabled:
        raise ApplyError("action_target.disabled", f"target {target_id} disabled")

    body_payload = payload.get("payload") or {}
    from_actor = _agent_actor_for(request)

    if target.mode == "async":
        return await _fire_action_async(
            session,
            request,
            target,
            target_id=target_id,
            body_payload=body_payload,
            from_actor=from_actor,
        )

    # Sync mode (default).
    result = await dispatch_target(
        session, target, body_payload, from_actor=from_actor
    )

    if result.get("ok"):
        lifecycle.mark_executed(request, result=result)
    else:
        lifecycle.mark_execution_failed(request, result=result)

    return ApplyResult(
        target_kind="action_target",
        target_id=target_id,
        extra={"execution_result": result},
    )


# ---------------------------------------------------------------------------
# append_log — direct path, never persisted as pending
# ---------------------------------------------------------------------------


async def apply_append_log(
    session: AsyncSession,
    *,
    module_id: str,
    lines: list[dict[str, Any]],
    actor: str,
) -> dict[str, Any]:
    """Append entries to a log_stream module.

    Returns ``{"appended": int, "truncated_count": int, "buffer_size": int}``.
    Raises :class:`ApplyError` if the module is not a log_stream.
    """
    row = await session.get(Module, module_id)
    if row is None or row.deleted_at is not None:
        raise ApplyError("module.not_found", f"module {module_id} not found")
    if row.type != "log_stream":
        raise ApplyError("module.wrong_type", f"module {module_id} is not a log_stream")

    cfg = json.loads(row.config or "{}")
    data = json.loads(row.data or "{}")
    ring = int(cfg.get("ring_buffer_size", 200))
    entries: list[dict[str, Any]] = list(data.get("entries", []))

    # Coerce lines into the Entry schema (timestamp defaults to now, level/severity).
    now = utcnow_iso()
    new_entries: list[dict[str, Any]] = []
    for raw in lines:
        entry = {
            "t": raw.get("t") or raw.get("ts") or now,
            "message": str(raw.get("message", "")),
        }
        sev = raw.get("severity") or raw.get("level")
        if sev:
            entry["severity"] = sev
        src = raw.get("source") or (raw.get("fields") or {}).get("source")
        if src:
            entry["source"] = src
        if raw.get("icon"):
            entry["icon"] = raw["icon"]
        new_entries.append(entry)

    appended = len(new_entries)
    combined = entries + new_entries
    truncated_count = max(0, len(combined) - ring)
    if truncated_count:
        combined = combined[-ring:]

    data["entries"] = combined
    data["last_appended_at"] = now

    # Re-validate against the module schema to keep the table-level invariant.
    try:
        clean_data = module_registry.validate_data("log_stream", data)
    except Exception as exc:
        raise ApplyError("module.invalid_payload", str(exc)) from exc

    row.data = json.dumps(clean_data)
    row.version += 1
    row.updated_at = now
    row.last_updated_by = actor
    await session.flush()

    # Phase 5: small append event (entries only, not the full module).
    publish_after_commit(
        session,
        f"log_stream:{module_id}",
        "log_appended",
        {
            "module_id": module_id,
            "entries": new_entries,
            "buffer_size": len(combined),
            "truncated_count": truncated_count,
            "version": row.version,
            "updated_at": now,
        },
    )
    # Also notify page-level subscribers that the module updated (no payload).
    publish_after_commit(
        session,
        f"page:{row.page_id}",
        "module_updated",
        {"module": _module_summary(row)},
    )
    publish_after_commit(
        session,
        f"module:{module_id}",
        "module_updated",
        {"module": _module_summary(row)},
    )

    return {
        "appended": appended,
        "truncated_count": truncated_count,
        "buffer_size": len(combined),
    }


# ---------------------------------------------------------------------------
# register_file
# ---------------------------------------------------------------------------


async def apply_register_file(
    session: AsyncSession, request: ApprovalRequest
) -> ApplyResult:
    """Move a dropped inbox file into the managed store and create a files row.

    Re-validates that the inbox file still exists and is byte-for-byte what the
    agent registered (the admin may approve days later). A vanished or changed
    file fails the apply rather than serving bytes the admin never reviewed.
    """
    payload = _load_payload(request)
    settings = get_settings()
    inbox_root = settings.resolved_files_inbox_path()
    store_root = settings.resolved_files_store_path()
    page_id = payload.get("page_id")

    try:
        src = resolve_inbox_file(inbox_root, page_id, payload["inbox_name"])
    except FilePathError as exc:
        raise ApplyError("file.invalid_name", str(exc)) from exc
    if not src.is_file():
        raise ApplyError(
            "file.not_in_inbox", f"{payload['inbox_name']!r} is no longer in the inbox"
        )
    size, sha = stat_and_sha256(src)
    if size != payload.get("size_bytes") or sha != payload.get("sha256"):
        raise ApplyError(
            "file.changed", "inbox file changed since the registration was submitted"
        )

    fil_id = payload.get("provisional_id") or new_id("fil")
    # Move just before the (final, fallible) flush to keep the rollback window
    # tiny; a rolled-back flush leaves a store-orphan that reconcile surfaces.
    row = persist_registered_file(
        session,
        file_id=fil_id,
        agent_id=request.agent_id,
        src=src,
        store_root=store_root,
        inbox_name=payload["inbox_name"],
        display_name=payload["display_name"],
        kind=payload["kind"],
        mime=payload["mime"],
        sha256=sha,
        size_bytes=size,
        page_id=page_id,
        purpose=payload.get("purpose"),
    )
    await session.flush()

    # target_kind stays None (the CHECK only allows module/page/action_target);
    # we just point target_id at the new file for traceability.
    request.target_id = fil_id
    publish_after_commit(session, "files", "file_registered", {"file": file_summary(row)})
    return ApplyResult(
        target_kind=None,
        target_id=fil_id,
        extra={"file_id": fil_id, "url": f"/api/v1/files/{fil_id}/raw"},
    )


# ---------------------------------------------------------------------------
# register_agent
# ---------------------------------------------------------------------------


async def apply_register_agent(
    session: AsyncSession, request: ApprovalRequest
) -> ApplyResult:
    """Approve a pending agent self-registration (mint happens on client claim)."""
    if request.target_kind != "agent_registration" or not request.target_id:
        raise ApplyError(
            "registration.invalid_target",
            "register_agent requires target_kind=agent_registration",
        )
    row = await session.get(AgentRegistrationRequest, request.target_id)
    if row is None:
        raise ApplyError("registration.not_found", request.target_id)
    if row.status != "pending":
        raise ApplyError(
            "registration.not_pending",
            f"registration is {row.status!r}",
        )
    payload = _load_payload(request)
    try:
        await approve_registration_row(
            session,
            row,
            decided_by="approval:apply",
            display_name=payload.get("display_name"),
            description=payload.get("description"),
            permissions=payload.get("permissions"),
        )
    except ProblemDetail as exc:
        raise ApplyError(exc.code, exc.detail or exc.title) from exc
    return ApplyResult(
        target_kind="agent_registration",
        target_id=row.id,
        extra={"requested_name": row.requested_name},
    )


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------


_DISPATCH = {
    "create_module": apply_create_module,
    "update_module_data": apply_update_module,
    "update_module_config": apply_update_module,
    "update_module_meta": apply_update_module,
    "delete_module": apply_delete_module,
    "create_page": apply_create_page,
    "delete_page": apply_delete_page,
    "fire_action_button": apply_fire_action,
    "register_file": apply_register_file,
    "register_agent": apply_register_agent,
}


async def apply_request(
    session: AsyncSession,
    request: ApprovalRequest,
    *,
    actor: str,
) -> ApplyResult:
    """Dispatch to the action-specific apply function.

    The caller is responsible for flipping the request's status to
    ``approved`` before calling this; this function then flips it to
    ``applied`` (or, for fire_action, sets ``executed_at`` /
    ``execution_result``).

    On failure, raises :class:`ApplyError`; the caller should then call
    :func:`lifecycle.mark_application_failed`.
    """
    if request.status != "approved":
        raise ApplyError(
            "lifecycle.invalid",
            f"cannot apply request in status {request.status}",
        )
    handler = _DISPATCH.get(request.action_type)
    if handler is None:
        raise ApplyError(
            "action_type.unknown",
            f"no apply handler for action_type {request.action_type!r}",
        )
    # fire_action_button manages its own executed_at; the lifecycle wants
    # applied set first so it can then move into executed/execution_failed.
    if request.action_type == "fire_action_button":
        lifecycle.mark_applied(request)
        result = await handler(session, request)
    else:
        result = await handler(session, request)
        lifecycle.mark_applied(request)
    return result


__all__ = [
    "ApplyError",
    "ApplyResult",
    "apply_append_log",
    "apply_create_module",
    "apply_create_page",
    "apply_delete_module",
    "apply_delete_page",
    "apply_fire_action",
    "apply_register_file",
    "apply_request",
    "apply_update_module",
    "dispatch_target",
    "secret_kv_key",
]
