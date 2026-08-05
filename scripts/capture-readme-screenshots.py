#!/usr/bin/env python
"""Capture README screenshots from a running local pdash UI.

Prerequisites:
  - Dev stack up at http://localhost:3000 (backend on :8080)
  - Playwright Chromium installed in this env:
      pip install playwright && playwright install chromium

Usage (from repo root):
  backend/.venv/Scripts/python scripts/capture-readme-screenshots.py
  # or on Unix:
  backend/.venv/bin/python scripts/capture-readme-screenshots.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "images"
DEFAULT_BASE = "http://localhost:3000"
DEFAULT_PASSWORD = "dev"


def _scrub_devtools(page) -> None:
    """Hide Next.js / ephemeral UI chrome that shouldn't appear in README shots."""
    page.evaluate(
        """() => {
          document.querySelectorAll(
            'nextjs-portal, [data-next-badge-root], [data-nextjs-toast], #__next-build-watcher'
          ).forEach((el) => el.remove());
          document.querySelectorAll('[data-sonner-toaster], [data-sonner-toast]').forEach((el) => {
            el.remove();
          });
          // Realtime connection pill ("reconnecting…" / "offline")
          document
            .querySelectorAll('[aria-label="Realtime connection status — dismiss"]')
            .forEach((el) => el.remove());
        }"""
    )


def _capture(page, path: Path, *, full_page: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _scrub_devtools(page)
    page.screenshot(path=str(path), full_page=full_page, type="png")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture pdash README screenshots.")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args(argv)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=2,
        )
        page = context.new_page()

        def goto_settle(url: str, *, extra_ms: int = 800) -> None:
            # Prefer load over networkidle: the app keeps an SSE EventSource open,
            # so networkidle often never fires on authenticated pages.
            page.goto(url, wait_until="load", timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(extra_ms)

        # Login page (pre-auth) — brand shot.
        goto_settle(f"{base}/login", extra_ms=400)
        page.evaluate("() => localStorage.setItem('pdash-theme', 'light')")
        page.reload(wait_until="load")
        page.wait_for_timeout(400)
        _capture(page, out / "login.png", full_page=False)

        # Sign in.
        page.fill("#password", args.password)
        page.click('button[type="submit"]')
        page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("() => localStorage.setItem('pdash-theme', 'light')")
        page.evaluate(
            "() => document.documentElement.setAttribute('data-theme', 'light')"
        )
        page.wait_for_timeout(800)

        # Home dashboard.
        goto_settle(base + "/", extra_ms=1200)  # charts / fonts settle
        _capture(page, out / "home.png", full_page=True)

        # Approvals inbox.
        goto_settle(f"{base}/approvals", extra_ms=1000)
        _capture(page, out / "approvals.png", full_page=True)

        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
