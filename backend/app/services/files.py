"""Shared helpers for the agent file-drop feature.

Agents write files into a per-page subfolder of the inbox dir on a shared host
mount, then register them. On approval the bytes are moved into the managed
store at ``<store>/<file_id>/blob`` and a ``files`` row is created. These helpers
are reused by the approval apply handler and the admin manual-register endpoint
so the validation / hashing / move logic lives in exactly one place.

Security: every filename the agent supplies is reduced to a bare basename and
checked for containment before it touches disk; the serve route never accepts a
raw path, only a ``fil_*`` id resolved to a DB row.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FileRecord, utcnow_iso

# Page-id (and any inbox subfolder) segment charset. Page ids are prefixed
# ULIDs (``pg_...``); this is defense-in-depth in case a caller passes junk.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# Read/hash in 64 KiB chunks so we never load a whole file into memory.
_CHUNK = 64 * 1024

# MIME types we are willing to serve *inline* (Content-Disposition: inline) with
# their real Content-Type. Everything else is served as an attachment with
# ``application/octet-stream`` to neutralise stored-XSS (SVG/HTML/JS in
# particular are deliberately excluded).
INLINE_SAFE_MIMES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/plain",
    }
)


class FilePathError(ValueError):
    """Raised when an agent-supplied filename/segment is unsafe."""


def _validate_bare_name(name: str) -> None:
    if not name or name in (".", ".."):
        raise FilePathError("filename is empty or invalid")
    if "\x00" in name or "/" in name or "\\" in name:
        raise FilePathError("filename must not contain path separators")
    if name.startswith("."):
        raise FilePathError("dotfiles are not allowed")
    if Path(name).name != name:
        raise FilePathError("filename must be a bare basename")


def _validate_segment(segment: str) -> None:
    if not _SEGMENT_RE.match(segment):
        raise FilePathError(f"unsafe path segment: {segment!r}")


def page_inbox_dir(inbox_root: Path, page_id: str | None) -> Path:
    """Directory an agent should drop a file into for ``page_id`` (or the root)."""
    if page_id:
        _validate_segment(page_id)
        return inbox_root / page_id
    return inbox_root


def resolve_inbox_file(inbox_root: Path, page_id: str | None, name: str) -> Path:
    """Resolve ``name`` (dropped for ``page_id``) to an absolute path in the inbox.

    Raises :class:`FilePathError` if the name/segment is unsafe or the resolved
    path escapes the inbox root.
    """
    _validate_bare_name(name)
    base = page_inbox_dir(inbox_root, page_id)
    resolved = (base / name).resolve()
    root = inbox_root.resolve()
    if not resolved.is_relative_to(root):
        raise FilePathError("resolved path escapes the inbox")
    return resolved


def resolve_stored_file(store_root: Path, stored_path: str) -> Path:
    """Resolve a ``files.stored_path`` (e.g. ``fil_x/blob``) to an absolute path."""
    resolved = (store_root / stored_path).resolve()
    root = store_root.resolve()
    if not resolved.is_relative_to(root):
        raise FilePathError("resolved path escapes the store")
    return resolved


def stat_and_sha256(path: Path) -> tuple[int, str]:
    """Return ``(size_bytes, sha256_hex)`` by streaming the file once."""
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return size, h.hexdigest()


def guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def classify_kind(mime: str) -> str:
    """``image`` for displayable images, ``document`` for everything else."""
    return "image" if mime.startswith("image/") else "document"


def is_inline_safe(mime: str) -> bool:
    return mime in INLINE_SAFE_MIMES


def move_into_store(src: Path, store_root: Path, file_id: str) -> str:
    """Move ``src`` into ``<store>/<file_id>/blob``. Returns the relative path."""
    dest_dir = store_root / file_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "blob"
    shutil.move(str(src), str(dest))
    return f"{file_id}/blob"


def remove_stored_file(store_root: Path, stored_path: str | None) -> None:
    """Best-effort delete of a stored blob and its ``<file_id>/`` dir."""
    if not stored_path:
        return
    try:
        blob = resolve_stored_file(store_root, stored_path)
    except FilePathError:
        return
    try:
        blob.unlink(missing_ok=True)
        parent = blob.parent
        if parent != store_root.resolve():
            parent.rmdir()
    except OSError:
        pass


def persist_registered_file(
    session: AsyncSession,
    *,
    file_id: str,
    agent_id: str | None,
    src: Path,
    store_root: Path,
    inbox_name: str,
    display_name: str,
    kind: str,
    mime: str,
    sha256: str,
    size_bytes: int,
    page_id: str | None,
    purpose: str | None,
) -> FileRecord:
    """Move ``src`` into the store and add a ``files`` row (caller flushes).

    Shared by the approval apply handler and the admin manual-register endpoint
    so the move + insert happen identically. The move is the last fs op before
    the row insert, keeping the rollback window small.
    """
    now = utcnow_iso()
    stored_path = move_into_store(src, store_root, file_id)
    row = FileRecord(
        id=file_id,
        agent_id=agent_id,
        inbox_name=inbox_name,
        display_name=display_name,
        stored_path=stored_path,
        sha256=sha256,
        size_bytes=size_bytes,
        mime=mime,
        kind=kind,
        status="registered",
        page_id=page_id,
        purpose=purpose,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    return row


def file_to_dict(row: FileRecord) -> dict[str, Any]:
    """Full serialization for admin/agent API responses."""
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "inbox_name": row.inbox_name,
        "display_name": row.display_name,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "mime": row.mime,
        "kind": row.kind,
        "status": row.status,
        "page_id": row.page_id,
        "purpose": row.purpose,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "url": f"/api/v1/files/{row.id}/raw",
    }


def file_summary(row: FileRecord) -> dict[str, Any]:
    """Slim representation for SSE events."""
    return {
        "id": row.id,
        "display_name": row.display_name,
        "kind": row.kind,
        "mime": row.mime,
        "size_bytes": row.size_bytes,
        "page_id": row.page_id,
        "status": row.status,
    }


__all__ = [
    "FilePathError",
    "INLINE_SAFE_MIMES",
    "classify_kind",
    "file_summary",
    "file_to_dict",
    "guess_mime",
    "is_inline_safe",
    "move_into_store",
    "page_inbox_dir",
    "persist_registered_file",
    "remove_stored_file",
    "resolve_inbox_file",
    "resolve_stored_file",
    "stat_and_sha256",
]
