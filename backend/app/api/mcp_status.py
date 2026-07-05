"""MCP control center — aggregated status for the admin UI.

The frontend can only reach the backend, so this endpoint probes the MCP
server's ``/info`` route (service-secret–gated) and merges the result with
backend-side facts (version, whether the service secret is configured, the
screenshot sidecar state). It never raises on an unreachable MCP server — it
returns ``reachable=false`` with an ``error`` string so the UI can render a
"down" state. Mirrors the screenshot-sidecar probe in ``api/internal.py``.
"""

from __future__ import annotations

from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import CurrentUser, require_session
from ..auth.secrets import KEY_SERVICE_SECRET, get_kv
from ..config import get_settings
from ..db import read_session
from ..version import app_version

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class McpToolOut(BaseModel):
    name: str
    description: str
    category: Literal["read", "write", "bootstrap"]


class ScreenshotSidecarOut(BaseModel):
    configured: bool
    reachable: bool | None = None


class McpStatusOut(BaseModel):
    reachable: bool
    error: str | None = None
    mcp_url: str
    mcp_version: str | None = None
    sse_connected: bool | None = None
    auth_cache_ttl_s: float | None = None
    idem_dedupe_ttl_s: float | None = None
    tools: list[McpToolOut] = []
    backend_version: str
    service_secret_configured: bool
    screenshot_sidecar: ScreenshotSidecarOut


async def _probe_screenshot(url: str, timeout: float) -> bool | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url.rstrip("/") + "/healthz")
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


@router.get("/status", response_model=McpStatusOut)
async def mcp_status(
    _: Annotated[CurrentUser, Depends(require_session)],
    session: Annotated[AsyncSession, Depends(read_session)],
) -> McpStatusOut:
    settings = get_settings()
    secret = await get_kv(session, KEY_SERVICE_SECRET)
    timeout = settings.mcp_probe_timeout_seconds

    screenshot_url = settings.screenshot_service_url
    sidecar = ScreenshotSidecarOut(
        configured=bool(screenshot_url),
        reachable=(await _probe_screenshot(screenshot_url, timeout) if screenshot_url else None),
    )

    base = McpStatusOut(
        reachable=False,
        mcp_url=settings.mcp_url,
        backend_version=app_version(),
        service_secret_configured=bool(secret),
        screenshot_sidecar=sidecar,
    )

    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(settings.mcp_url.rstrip("/") + "/info", headers=headers)
    except httpx.HTTPError as exc:
        base.error = f"MCP server unreachable: {exc}"
        return base

    if resp.status_code != 200:
        base.error = f"MCP /info returned {resp.status_code}"
        return base

    info = resp.json()
    base.reachable = True
    base.mcp_version = info.get("version")
    base.sse_connected = info.get("sse_connected")
    base.auth_cache_ttl_s = info.get("auth_cache_ttl_s")
    base.idem_dedupe_ttl_s = info.get("idem_dedupe_ttl_s")
    base.tools = [
        McpToolOut(
            name=t.get("name", ""),
            description=t.get("description", ""),
            category=(
                t["category"]
                if t.get("category") in ("read", "write", "bootstrap")
                else "read"
            ),
        )
        for t in info.get("tools", [])
    ]
    return base
