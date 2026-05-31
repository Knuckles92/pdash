"""Screenshot sidecar service.

A deliberately tiny FastAPI app that renders a URL in headless Chromium and
returns a PNG. The pdash backend (never an agent directly) calls ``POST
/capture`` with the target URL and a session cookie it minted, so the captured
page is the real, authenticated dashboard.

Why a separate service: Chromium is a ~300-400MB dependency we don't want in the
core backend image. This sidecar runs only on the internal docker network (no
published ports) and, when ``PDASH_SERVICE_SECRET`` is set, requires the same
Bearer secret the backend↔MCP hop uses.

Env:
  PDASH_SERVICE_SECRET            — require ``Authorization: Bearer <it>``. If
                                    unset, /capture is refused (503) unless
                                    PDASH_SCREENSHOT_ALLOW_NO_AUTH is set.
  PDASH_SCREENSHOT_ALLOW_NO_AUTH  — opt out of the secret requirement (no-auth).
  PDASH_SCREENSHOT_NAV_TIMEOUT_MS — navigation timeout (default 20000).
  PDASH_SCREENSHOT_MAX_HEIGHT_PX  — clamp full-page capture height (default 8000).
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field
from playwright.async_api import Browser, async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pdash-screenshot")

_SERVICE_SECRET = os.environ.get("PDASH_SERVICE_SECRET", "")
# Fail closed: with no secret, /capture is refused unless the operator
# explicitly opts into no-auth (e.g. a fully-trusted, isolated network).
_ALLOW_NO_AUTH = os.environ.get("PDASH_SCREENSHOT_ALLOW_NO_AUTH", "").lower() in (
    "1",
    "true",
    "yes",
)
_NAV_TIMEOUT_MS = int(os.environ.get("PDASH_SCREENSHOT_NAV_TIMEOUT_MS", "20000"))
_MAX_HEIGHT_PX = int(os.environ.get("PDASH_SCREENSHOT_MAX_HEIGHT_PX", "8000"))


class Cookie(BaseModel):
    name: str
    value: str
    url: str


class CaptureIn(BaseModel):
    url: str
    cookies: list[Cookie] = Field(default_factory=list)
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=1024, ge=320, le=4320)
    full_page: bool = True
    # Extra settle time after networkidle for charts/animations to paint.
    wait_ms: int = Field(default=600, ge=0, le=10000)


class _BrowserManager:
    """Owns a single long-lived Chromium; each capture gets a fresh context."""

    def __init__(self) -> None:
        self._pw = None
        self._browser: Browser | None = None
        # Serialize captures: one admin, low volume — avoids piling up contexts.
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if not _SERVICE_SECRET:
            if _ALLOW_NO_AUTH:
                logger.warning(
                    "PDASH_SERVICE_SECRET is unset and PDASH_SCREENSHOT_ALLOW_NO_AUTH "
                    "is enabled: /capture is UNAUTHENTICATED. Only run this on a "
                    "fully-trusted, isolated network."
                )
            else:
                logger.warning(
                    "PDASH_SERVICE_SECRET is unset: /capture will reject all requests "
                    "(503) until a secret is configured. Set PDASH_SERVICE_SECRET or "
                    "PDASH_SCREENSHOT_ALLOW_NO_AUTH=1."
                )
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        logger.info("chromium launched")

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()

    async def capture(self, spec: CaptureIn) -> bytes:
        if self._browser is None:
            raise RuntimeError("browser not started")
        async with self._lock:
            context = await self._browser.new_context(
                viewport={"width": spec.viewport_width, "height": spec.viewport_height},
                device_scale_factor=1,
            )
            try:
                if spec.cookies:
                    await context.add_cookies(
                        [
                            {"name": c.name, "value": c.value, "url": c.url}
                            for c in spec.cookies
                        ]
                    )
                page = await context.new_page()
                await page.goto(spec.url, wait_until="networkidle", timeout=_NAV_TIMEOUT_MS)
                if spec.wait_ms:
                    await page.wait_for_timeout(spec.wait_ms)
                if spec.full_page:
                    # full_page captures the whole scroll height; cap a runaway
                    # tall page by clipping to _MAX_HEIGHT_PX instead.
                    scroll_h = await page.evaluate("() => document.body.scrollHeight")
                    if isinstance(scroll_h, (int, float)) and scroll_h > _MAX_HEIGHT_PX:
                        return await page.screenshot(
                            type="png",
                            clip={
                                "x": 0,
                                "y": 0,
                                "width": spec.viewport_width,
                                "height": _MAX_HEIGHT_PX,
                            },
                        )
                return await page.screenshot(full_page=spec.full_page, type="png")
            finally:
                await context.close()


_manager = _BrowserManager()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await _manager.start()
    try:
        yield
    finally:
        await _manager.stop()


app = FastAPI(title="pdash-screenshot", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


def _check_auth(authorization: str | None) -> None:
    if not _SERVICE_SECRET:
        # Fail closed unless the operator explicitly allowed no-auth.
        if _ALLOW_NO_AUTH:
            return
        raise HTTPException(
            status_code=503,
            detail=(
                "screenshot service has no PDASH_SERVICE_SECRET configured; "
                "set it (recommended) or PDASH_SCREENSHOT_ALLOW_NO_AUTH=1 to opt out"
            ),
        )
    if authorization != f"Bearer {_SERVICE_SECRET}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/capture")
async def capture(
    spec: CaptureIn,
    authorization: str | None = Header(default=None),
) -> Response:
    _check_auth(authorization)
    try:
        png = await _manager.capture(spec)
    except Exception as exc:  # noqa: BLE001 — report any capture failure as 500
        logger.exception("capture failed for %s", spec.url)
        raise HTTPException(status_code=500, detail=f"capture failed: {exc}") from exc
    return Response(content=png, media_type="image/png")
