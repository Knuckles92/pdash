"""File serving + admin reconciliation endpoints (``/api/v1/files/*``).

All routes are admin-session authed (the dashboard is Tailscale-only, single
admin). Serving is deliberately conservative: only a tiny allowlist of MIME
types is served inline; everything else is forced to a download as
``application/octet-stream`` to neutralise stored-XSS (SVG/HTML/JS especially).

The admin surface lists registered files plus an inbox scan so orphaned drops
(files an agent never registered) and store-orphans (rolled-back applies) are
visible and cleanable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import CurrentUser, require_csrf, require_session
from ..config import get_settings
from ..db import get_session, read_session
from ..errors import bad_request, not_found
from ..events.publish import publish_after_commit
from ..ids import new_id
from ..models import ApprovalRequest, FileRecord, Page, utcnow_iso
from ..services.audit import write_event
from ..services.files import (
    FilePathError,
    classify_kind,
    file_summary,
    file_to_dict,
    guess_mime,
    is_inline_safe,
    persist_registered_file,
    remove_stored_file,
    resolve_inbox_file,
    resolve_stored_file,
    stat_and_sha256,
)

router = APIRouter(prefix="/api/v1/files", tags=["files"])

# Cap the inbox scan so a pathological dir can't stall the admin UI.
_SCAN_CAP = 1000


class InboxRegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=200)
    page_id: str | None = None
    purpose: str | None = Field(default=None, max_length=1000)


class InboxDeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    page_id: str | None = None


def _iso_from_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _content_disposition(kind: str, display_name: str, ext: str) -> str:
    name = display_name if (not ext or display_name.endswith(ext)) else display_name + ext
    ascii_fallback = name.encode("ascii", "ignore").decode() or "download"
    return f"{kind}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(name)}"


# ---------------------------------------------------------------------------
# Admin: list / reconcile
# ---------------------------------------------------------------------------


async def _scan_inbox(
    session: AsyncSession, inbox_root: Path, store_root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int], bool]:
    """Return ``(inbox_items, store_orphans, counts, truncated)``."""
    # Index pending register_file requests by (page_id, inbox_name).
    pending_rows = (
        await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == "pending",
                ApprovalRequest.action_type == "register_file",
            )
        )
    ).scalars().all()
    pending_index: dict[tuple[str | None, str], str] = {}
    for pr in pending_rows:
        payload = json.loads(pr.proposed_payload or "{}")
        pending_index[(payload.get("page_id"), payload.get("inbox_name"))] = pr.id

    inbox_items: list[dict[str, Any]] = []
    unclaimed = 0
    pending = 0
    truncated = False
    root = inbox_root.resolve()
    if root.exists():
        count = 0
        for entry in sorted(root.rglob("*")):
            if not entry.is_file():
                continue
            count += 1
            if count > _SCAN_CAP:
                truncated = True
                break
            rel = entry.relative_to(root)
            parts = rel.parts
            if len(parts) == 1:
                page_id, name = None, parts[0]
            elif len(parts) == 2:
                page_id, name = parts[0], parts[1]
            else:
                # Deeper nesting isn't part of the layout; skip it.
                continue
            req_id = pending_index.get((page_id, name))
            status = "pending_registration" if req_id else "unclaimed"
            if req_id:
                pending += 1
            else:
                unclaimed += 1
            st = entry.stat()
            mime = guess_mime(name)
            inbox_items.append(
                {
                    "name": name,
                    "page_id": page_id,
                    "size_bytes": st.st_size,
                    "modified_at": _iso_from_mtime(st.st_mtime),
                    "mime": mime,
                    "kind": classify_kind(mime),
                    "status": status,
                    "request_id": req_id,
                }
            )

    # Store-orphans: <fil_*>/blob dirs with no matching registered row.
    store_orphans: list[dict[str, Any]] = []
    sroot = store_root.resolve()
    if sroot.exists():
        for child in sorted(sroot.iterdir()):
            if not (child.is_dir() and child.name.startswith("fil_")):
                continue
            blob = child / "blob"
            if not blob.is_file():
                continue
            row = await session.get(FileRecord, child.name)
            if row is None or row.status != "registered":
                store_orphans.append(
                    {"file_id": child.name, "size_bytes": blob.stat().st_size}
                )

    counts = {"unclaimed": unclaimed, "pending": pending, "store_orphans": len(store_orphans)}
    return inbox_items, store_orphans, counts, truncated


@router.get("")
async def list_files(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> dict[str, Any]:
    """Registered files + an inbox scan (orphans) + store-orphans + counts."""
    settings = get_settings()
    store_root = settings.resolved_files_store_path()
    inbox_root = settings.resolved_files_inbox_path()

    rows = (
        await session.execute(
            select(FileRecord)
            .where(FileRecord.status == "registered")
            .order_by(FileRecord.created_at.desc())
            .limit(1000)
        )
    ).scalars().all()
    files: list[dict[str, Any]] = []
    missing = 0
    for r in rows:
        d = file_to_dict(r)
        present = False
        if r.stored_path:
            try:
                present = resolve_stored_file(store_root, r.stored_path).is_file()
            except FilePathError:
                present = False
        d["present_on_disk"] = present
        if not present:
            missing += 1
        files.append(d)

    inbox_items, store_orphans, counts, truncated = await _scan_inbox(
        session, inbox_root, store_root
    )
    counts = {"registered": len(files), "missing": missing, **counts}
    return {
        "files": files,
        "inbox": inbox_items,
        "store_orphans": store_orphans,
        "counts": counts,
        "scan_truncated": truncated,
        "total_unclaimed": counts["unclaimed"] + counts["missing"],
    }


@router.get("/orphan-count")
async def orphan_count(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> dict[str, int]:
    """Lean counts for the Files-tab badge (no full file lists serialized).

    Declared before ``/{file_id}`` so the literal path wins over the param route.
    """
    settings = get_settings()
    store_root = settings.resolved_files_store_path()
    inbox_root = settings.resolved_files_inbox_path()

    rows = (
        await session.execute(
            select(FileRecord).where(FileRecord.status == "registered")
        )
    ).scalars().all()
    missing = 0
    for r in rows:
        present = False
        if r.stored_path:
            try:
                present = resolve_stored_file(store_root, r.stored_path).is_file()
            except FilePathError:
                present = False
        if not present:
            missing += 1

    counts = (await _scan_inbox(session, inbox_root, store_root))[2]
    return {
        "unclaimed": counts["unclaimed"],
        "pending": counts["pending"],
        "missing": missing,
        "total": counts["unclaimed"] + missing,
    }


# ---------------------------------------------------------------------------
# Admin: inbox mutations (manual register / delete)
# ---------------------------------------------------------------------------


@router.post("/inbox/register")
async def register_inbox_file(
    body: InboxRegisterIn,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Admin manually registers an orphaned inbox file (no approval needed)."""
    settings = get_settings()
    inbox_root = settings.resolved_files_inbox_path()
    store_root = settings.resolved_files_store_path()

    if body.page_id is not None:
        page = await session.get(Page, body.page_id)
        if page is None or page.deleted_at is not None:
            raise not_found("page.not_found", body.page_id)

    try:
        src = resolve_inbox_file(inbox_root, body.page_id, body.name)
    except FilePathError as exc:
        raise bad_request("file.invalid_name", str(exc)) from exc
    if not src.is_file():
        raise not_found("file.not_in_inbox", body.name)

    size, sha = stat_and_sha256(src)
    mime = guess_mime(body.name)
    row = persist_registered_file(
        session,
        file_id=new_id("fil"),
        agent_id=None,
        src=src,
        store_root=store_root,
        inbox_name=body.name,
        display_name=body.display_name,
        kind=classify_kind(mime),
        mime=mime,
        sha256=sha,
        size_bytes=size,
        page_id=body.page_id,
        purpose=body.purpose,
    )
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type="register_file",
        target_kind=None,
        target_id=row.id,
        outcome="applied",
        payload_summary={
            "inbox_name": body.name,
            "display_name": body.display_name,
            "admin_manual": True,
        },
    )
    publish_after_commit(session, "files", "file_registered", {"file": file_summary(row)})
    return file_to_dict(row)


@router.post("/inbox/delete", status_code=204)
async def delete_inbox_file(
    body: InboxDeleteIn,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Delete an unclaimed file from the inbox."""
    settings = get_settings()
    inbox_root = settings.resolved_files_inbox_path()
    try:
        src = resolve_inbox_file(inbox_root, body.page_id, body.name)
    except FilePathError as exc:
        raise bad_request("file.invalid_name", str(exc)) from exc
    if not src.is_file():
        raise not_found("file.not_in_inbox", body.name)
    src.unlink()
    await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type="delete_inbox_file",
        target_kind=None,
        target_id=None,
        outcome="applied",
        payload_summary={"inbox_name": body.name, "page_id": body.page_id},
    )
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Serving (id-addressed only; never an arbitrary path)
# ---------------------------------------------------------------------------


async def _serve(
    file_id: str, session: AsyncSession, *, force_attachment: bool
) -> FileResponse:
    settings = get_settings()
    row = await session.get(FileRecord, file_id)
    if row is None or row.status != "registered" or row.stored_path is None:
        raise not_found("file.not_found", file_id)
    store_root = settings.resolved_files_store_path()
    try:
        path = resolve_stored_file(store_root, row.stored_path)
    except FilePathError as exc:
        raise not_found("file.not_found", file_id) from exc
    if not path.is_file():
        raise not_found("file.missing_on_disk", file_id)

    inline = (not force_attachment) and is_inline_safe(row.mime)
    media_type = row.mime if inline else "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    ext = Path(row.inbox_name).suffix
    headers = {
        "Content-Disposition": _content_disposition(disposition, row.display_name, ext),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=0, must-revalidate",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
    return FileResponse(path, media_type=media_type, headers=headers)


@router.get("/{file_id}/raw")
async def serve_raw(
    file_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> FileResponse:
    """Serve the file for in-dashboard display (inline only for safe types)."""
    return await _serve(file_id, session, force_attachment=False)


@router.get("/{file_id}/download")
async def serve_download(
    file_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> FileResponse:
    """Always force a download regardless of MIME."""
    return await _serve(file_id, session, force_attachment=True)


@router.get("/{file_id}")
async def get_file(
    file_id: str,
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> dict[str, Any]:
    row = await session.get(FileRecord, file_id)
    if row is None or row.status != "registered":
        raise not_found("file.not_found", file_id)
    return file_to_dict(row)


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: str,
    user: Annotated[CurrentUser, Depends(require_csrf)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Soft-delete a registered file and remove its bytes from the store."""
    row = await session.get(FileRecord, file_id)
    if row is None or row.status == "deleted":
        raise not_found("file.not_found", file_id)
    settings = get_settings()
    remove_stored_file(settings.resolved_files_store_path(), row.stored_path)
    now = utcnow_iso()
    row.status = "deleted"
    row.deleted_at = now
    row.updated_at = now
    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id=user.name,
        action_type="delete_file",
        target_kind=None,
        target_id=file_id,
        outcome="applied",
        payload_summary={"display_name": row.display_name},
    )
    publish_after_commit(session, "files", "file_removed", {"file_id": file_id})
    return Response(status_code=204)
