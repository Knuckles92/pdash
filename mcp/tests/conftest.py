"""End-to-end fixtures: a live FastAPI backend running in a subprocess.

Each test gets a fresh DB by spinning up uvicorn from the backend's venv on
an ephemeral port. The backend is initialised via ``app.cli init`` so the
service_secret + admin password are real; tests log in as admin and create
agents for the MCP server to talk to.

Skips with a clear message when the backend's venv isn't present.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
BACKEND_PY = BACKEND_ROOT / ".venv" / "bin" / "python"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class BackendHandle:
    base_url: str
    service_secret: str
    admin_password: str
    proc: subprocess.Popen
    db_path: Path

    def http(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=10.0)


def _wait_for(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.1)
    raise RuntimeError(f"backend never came up at {url}: {last_err!r}")


@pytest.fixture(scope="function")
def live_backend() -> Generator[BackendHandle, None, None]:
    if not BACKEND_PY.exists():
        pytest.skip(f"backend venv not present at {BACKEND_PY}")

    tmpdir = Path(tempfile.mkdtemp(prefix="pdash-mcp-test-"))
    db_path = tmpdir / "test.db"
    admin_password = "test1234"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["PDASH_DATABASE_PATH"] = str(db_path)
    env["PYTHONUNBUFFERED"] = "1"

    # 1) Bootstrap: run `app.cli init` to create the DB + secrets.
    init = subprocess.run(
        [str(BACKEND_PY), "-m", "app.cli", "init", "--admin-password", admin_password],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if init.returncode != 0:
        raise RuntimeError(f"backend init failed:\n{init.stdout}\n{init.stderr}")
    # Parse the printed secret. The CLI emits:
    #   Service secret (store this ...):
    #     <secret>
    service_secret = ""
    lines = [ln.rstrip() for ln in init.stdout.splitlines()]
    for i, line in enumerate(lines):
        if "Service secret" in line and i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            if candidate and not candidate.startswith("="):
                service_secret = candidate
                break
    if not service_secret:
        raise RuntimeError(
            f"could not parse service_secret from init output:\n{init.stdout}"
        )

    # 2) Launch uvicorn against the same DB.
    proc = subprocess.Popen(
        [
            str(BACKEND_PY), "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "warning",
        ],
        cwd=str(BACKEND_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for(f"{base_url}/healthz")
    except Exception:
        proc.terminate()
        out = proc.stdout.read().decode() if proc.stdout else ""
        raise RuntimeError(f"backend failed to start:\n{out}")

    handle = BackendHandle(
        base_url=base_url,
        service_secret=service_secret,
        admin_password=admin_password,
        proc=proc,
        db_path=db_path,
    )
    try:
        yield handle
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        try:
            tmpdir.rmdir()
        except OSError:
            pass


@dataclass
class AdminSession:
    """An admin httpx.Client with session cookies and X-CSRF-Token set."""

    client: httpx.Client
    csrf: str


@pytest.fixture
def admin(live_backend: BackendHandle) -> Generator[AdminSession, None, None]:
    c = live_backend.http()
    r = c.post("/api/v1/auth/login", json={"password": live_backend.admin_password})
    assert r.status_code == 200, r.text
    csrf = c.cookies.get("csrf_token")
    assert csrf
    c.headers.update({"X-CSRF-Token": csrf})
    try:
        yield AdminSession(client=c, csrf=csrf)
    finally:
        c.close()


def register_agent(admin: AdminSession, name: str = "mcp-test-agent") -> tuple[str, str]:
    r = admin.client.post("/api/v1/agents", json={"display_name": name})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["agent"]["id"], body["api_key"]


def home_page_id(admin: AdminSession) -> str:
    r = admin.client.get("/api/v1/pages")
    return next(p["id"] for p in r.json()["items"] if p["slug"] == "home")


@pytest.fixture
def mcp_backend_client(live_backend: BackendHandle):
    """A pdash-mcp ``BackendClient`` pointed at the live backend.

    Constructed lazily and closed by garbage collection — explicit close is
    skipped because httpx async clients can't be closed from a fresh event
    loop after their original loop is gone (pytest-asyncio creates a new
    loop per test). The httpx client's `__del__` flushes the connection
    pool which is fine for tests.
    """
    from app import backend as backend_mod
    from app import auth as auth_mod
    from app import idem
    from app import decision_cache

    # Reset module-level caches between tests.
    auth_mod.clear_cache()
    idem.clear_cache()
    decision_cache.clear_cache()

    c = backend_mod.BackendClient(
        base_url=live_backend.base_url,
        service_secret=live_backend.service_secret,
    )
    backend_mod.set_client_for_tests(c)
    try:
        yield c
    finally:
        backend_mod.set_client_for_tests(None)
        # Drop the reference; httpx will reclaim the connection pool.
        del c
