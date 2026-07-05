"""Shared helpers for Phase 3 tests."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient


def get_service_secret() -> str:
    """Read the service_secret stored in kv_settings by the conftest fixture."""
    from app.auth.secrets import KEY_SERVICE_SECRET, get_kv
    from app.db import get_sessionmaker

    sm = get_sessionmaker()

    async def _go() -> str:
        async with sm() as session:
            v = await get_kv(session, KEY_SERVICE_SECRET)
        return v or ""

    return asyncio.run(_go())


def register_agent(admin_client: TestClient, name: str = "claude-test") -> tuple[str, str]:
    """Create a fresh agent via the admin API; return (agent_id, plaintext_key)."""
    resp = admin_client.post("/api/v1/agents", json={"display_name": name})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["agent"]["id"], body["api_key"]


def internal_headers(
    agent_id: str,
    service_secret: str,
    *,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {service_secret}",
        "X-Agent-Id": agent_id,
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def home_page_id(client: TestClient) -> str:
    resp = client.get("/api/v1/pages")
    items = resp.json()["items"]
    return next(item["id"] for item in items if item["slug"] == "home")
