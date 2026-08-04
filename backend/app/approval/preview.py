"""Read-only dashboard preview for pending approval requests."""

from __future__ import annotations

import copy
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import modules as module_registry
from ..models import ActionTarget, AgentRegistrationRequest, ApprovalRequest, Module, Page, utcnow_iso
from ..services.redact import redact


def _module_to_dict(row: Module) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "owner_kind": row.owner_kind,
        "owner_id": row.owner_id,
        "page_id": row.page_id,
        "position": row.position,
        "grid": json.loads(row.grid) if row.grid else None,
        "permissions": json.loads(row.permissions or "{}"),
        "data": json.loads(row.data or "{}"),
        "config": json.loads(row.config or "{}"),
        "schema_version": row.schema_version,
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_updated_by": row.last_updated_by,
        "deleted_at": row.deleted_at,
    }



def _sort_modules(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        modules,
        key=lambda m: (m.get("position", 0), m.get("created_at", "")),
    )


def _page_summary(page: Page) -> dict[str, Any]:
    return {"id": page.id, "name": page.name, "slug": page.slug}


async def _load_page_modules(
    session: AsyncSession, page_id: str
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Module)
            .where(Module.page_id == page_id, Module.deleted_at.is_(None))
            .order_by(Module.position, Module.created_at)
        )
    ).scalars().all()
    return [_module_to_dict(r) for r in rows]


def _apply_update_patch(
    module: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """Merge patch into a module dict (mirrors apply_update_module)."""
    out = copy.deepcopy(module)
    mtype = out["type"]
    new_data = out["data"] if "data" not in patch else patch["data"]
    new_config = out["config"] if "config" not in patch else patch["config"]
    if "data" in patch or "config" in patch:
        new_data = module_registry.validate_data(mtype, new_data)
        new_config = module_registry.validate_config(mtype, new_config)
        out["data"] = new_data
        out["config"] = new_config
    if "title" in patch:
        out["title"] = patch["title"]
    if "position" in patch:
        out["position"] = patch["position"]
    if "page_id" in patch and patch["page_id"]:
        out["page_id"] = patch["page_id"]
    out["version"] = out.get("version", 0) + 1
    out["updated_at"] = utcnow_iso()
    return out


def _build_create_module(
    request: ApprovalRequest, payload: dict[str, Any]
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    mtype = payload["type"]
    clean_data = module_registry.validate_data(mtype, payload.get("data", {}))
    clean_config = module_registry.validate_config(mtype, payload.get("config", {}))
    mod_id = payload.get("provisional_id") or request.target_id or "mod_preview"
    now = utcnow_iso()
    synthetic = {
        "id": mod_id,
        "type": mtype,
        "title": payload.get("title"),
        "owner_kind": "agent",
        "owner_id": request.agent_id,
        "page_id": payload["page_id"],
        "position": payload.get("position", 0),
        "grid": payload.get("grid"),
        "permissions": payload.get("permissions") or {},
        "data": clean_data,
        "config": clean_config,
        "schema_version": 1,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "last_updated_by": f"agent:{request.agent_id}",
        "deleted_at": None,
    }
    highlight = {
        "module_ids": [mod_id],
        "removed_module_ids": [],
        "change": "create",
    }
    return payload["page_id"], synthetic, highlight


async def build_dashboard_preview(
    session: AsyncSession, request: ApprovalRequest
) -> dict[str, Any] | None:
    """Return a page-context preview payload, or None if unsupported."""
    payload = json.loads(request.proposed_payload or "{}")
    action = request.action_type

    if action == "create_page":
        pid = payload.get("provisional_id") or request.target_id or "pg_preview"
        return {
            "page": {
                "id": pid,
                "name": payload.get("name") or "Untitled page",
                "slug": payload.get("slug") or "",
                "description": payload.get("description"),
                # Prefer ``type``; fall back to legacy ``kind`` for in-flight approvals.
                "type": payload.get("type") or payload.get("kind") or "custom",
            },
            "modules": [],
            "highlight": {
                "module_ids": [],
                "removed_module_ids": [],
                "change": "create_page",
            },
        }

    if action == "create_module":
        page_id, synthetic, highlight = _build_create_module(request, payload)
        page = await session.get(Page, page_id)
        if page is None or page.deleted_at is not None:
            return None
        modules = await _load_page_modules(session, page_id)
        modules.append(synthetic)
        return {
            "page": _page_summary(page),
            "modules": _sort_modules(modules),
            "highlight": highlight,
        }

    if action in ("update_module_data", "update_module_config", "update_module_meta"):
        mod_id = payload.get("id") or request.target_id
        if not mod_id:
            return None
        row = await session.get(Module, mod_id)
        if row is None or row.deleted_at is not None:
            return None
        patch = payload.get("patch", {})
        current = _module_to_dict(row)
        updated = _apply_update_patch(current, patch)
        page_id = updated["page_id"]
        page = await session.get(Page, page_id)
        if page is None or page.deleted_at is not None:
            return None
        modules = await _load_page_modules(session, page_id)
        if updated["page_id"] != row.page_id:
            # Module moved to another page — show destination page without siblings
            # from the old page; only include the moved module on the new page.
            modules = [m for m in modules if m["id"] != mod_id]
            modules.append(updated)
        else:
            modules = [updated if m["id"] == mod_id else m for m in modules]
        return {
            "page": _page_summary(page),
            "modules": _sort_modules(modules),
            "highlight": {
                "module_ids": [mod_id],
                "removed_module_ids": [],
                "change": "update",
            },
        }

    if action == "delete_module":
        mod_id = payload.get("id") or request.target_id
        if not mod_id:
            return None
        row = await session.get(Module, mod_id)
        if row is None or row.deleted_at is not None:
            return None
        page = await session.get(Page, row.page_id)
        if page is None or page.deleted_at is not None:
            return None
        removed = _module_to_dict(row)
        modules = await _load_page_modules(session, row.page_id)
        modules = [m for m in modules if m["id"] != mod_id]
        return {
            "page": _page_summary(page),
            "modules": _sort_modules(modules),
            "highlight": {
                "module_ids": [],
                "removed_module_ids": [mod_id],
                "removed_modules": [removed],
                "change": "delete",
            },
        }

    return None


# ---------------------------------------------------------------------------
# fire_action_button — "what will be called" preview
# ---------------------------------------------------------------------------


def _action_destination(kind: str, cfg: dict[str, Any]) -> str | None:
    """Human-readable summary of where a fire_action will go.

    Mirrors the field names the dispatcher reads in ``apply.py`` so the admin
    sees the same target the apply step will hit.
    """
    if kind == "webhook":
        url = cfg.get("url")
        if not url:
            return None
        method = str(cfg.get("method", "POST")).upper()
        return f"{method} {url}"
    if kind == "mcp_tool":
        url = cfg.get("url")
        tool = cfg.get("tool_name")
        if url and tool:
            return f"{tool} @ {url}"
        return url or tool
    if kind == "local_script":
        cmd = cfg.get("command")
        if isinstance(cmd, list):
            return " ".join(str(part) for part in cmd)
        return cmd
    if kind == "agent_message":
        to = cfg.get("to_agent_id")
        return f"message → {to}" if to else None
    return None


async def build_action_preview(
    session: AsyncSession, request: ApprovalRequest
) -> dict[str, Any] | None:
    """Return a fire_action_button preview (target + effective payload), or None."""
    if request.action_type != "fire_action_button":
        return None
    payload = json.loads(request.proposed_payload or "{}")
    target_id = payload.get("target_id") or request.target_id
    if not target_id:
        return None
    target = await session.get(ActionTarget, target_id)
    if target is None or target.deleted_at is not None:
        return None

    cfg = redact(json.loads(target.config or "{}"))
    agent_payload = payload.get("payload") or {}
    uses_target_default = not agent_payload and target.kind == "webhook"
    effective = cfg.get("default_payload") or {} if uses_target_default else agent_payload

    return {
        "target": {
            "id": target.id,
            "name": target.name,
            "kind": target.kind,
            "mode": target.mode,
            "enabled": bool(target.enabled),
        },
        "destination": _action_destination(target.kind, cfg),
        "payload": redact(effective),
        "uses_target_default": uses_target_default,
    }


# ---------------------------------------------------------------------------
# register_file — file metadata preview
# ---------------------------------------------------------------------------


async def build_file_preview(
    session: AsyncSession, request: ApprovalRequest
) -> dict[str, Any] | None:
    """Return a register_file preview (file metadata + page hint), or None.

    The bytes still live in the inbox (unvetted, not yet served), so this is a
    metadata-only card — no thumbnail.
    """
    if request.action_type != "register_file":
        return None
    payload = json.loads(request.proposed_payload or "{}")

    page = None
    page_id = payload.get("page_id")
    if page_id:
        page_row = await session.get(Page, page_id)
        if page_row is not None and page_row.deleted_at is None:
            page = _page_summary(page_row)

    return {
        "display_name": payload.get("display_name"),
        "inbox_name": payload.get("inbox_name"),
        "kind": payload.get("kind"),
        "mime": payload.get("mime"),
        "size_bytes": payload.get("size_bytes"),
        "purpose": payload.get("purpose"),
        "sha256": payload.get("sha256"),
        "page": page,
    }


async def build_registration_preview(
    session: AsyncSession, request: ApprovalRequest
) -> dict[str, Any] | None:
    """Return a register_agent preview from the linked registration row."""
    if request.action_type != "register_agent":
        return None
    payload = json.loads(request.proposed_payload or "{}")
    row: AgentRegistrationRequest | None = None
    if request.target_kind == "agent_registration" and request.target_id:
        row = await session.get(AgentRegistrationRequest, request.target_id)
    return {
        "registration_id": request.target_id,
        "requested_name": row.requested_name if row else payload.get("display_name"),
        "description": row.description if row else payload.get("description"),
        "rationale": row.rationale if row else payload.get("rationale"),
        "client_hint": row.client_hint if row else payload.get("client_hint"),
        "status": row.status if row else None,
        "expires_at": row.expires_at if row else None,
    }


__all__ = [
    "build_action_preview",
    "build_dashboard_preview",
    "build_file_preview",
    "build_registration_preview",
]
