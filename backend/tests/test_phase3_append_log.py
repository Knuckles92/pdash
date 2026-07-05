"""Tests for ``POST /api/v1/internal/append-log``.

The default built-in ``update_module_data on owner_scope=self`` rule must
auto-apply when the calling agent owns the log_stream module. Ring buffer
trimming and ``truncated_count`` behavior is exercised here.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from _phase3_helpers import (
    get_service_secret,
    home_page_id,
    internal_headers,
    register_agent,
)


def _new_log_stream(admin_client: TestClient, *, page_id: str, agent_id: str, ring: int = 20) -> str:
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "log_stream",
            "page_id": page_id,
            "data": {"entries": []},
            "config": {"ring_buffer_size": ring},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_append_log_auto_applies_for_owner(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="log-owner")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    mod_id = _new_log_stream(admin_client, page_id=page_id, agent_id=agent_id)

    resp = admin_client.post(
        "/api/v1/internal/append-log",
        json={
            "module_id": mod_id,
            "lines": [
                {"message": "first", "level": "info"},
                {"message": "second", "level": "warning"},
            ],
        },
        headers=internal_headers(agent_id, secret, idempotency_key="log-1"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "applied"
    assert body["appended"] == 2
    assert body["buffer_size"] == 2

    # Module should now have the entries
    fetched = admin_client.get(f"/api/v1/modules/{mod_id}")
    entries = fetched.json()["data"]["entries"]
    assert [e["message"] for e in entries] == ["first", "second"]


def test_append_log_ring_buffer_trims_with_truncated_count(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="log-trim")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    mod_id = _new_log_stream(admin_client, page_id=page_id, agent_id=agent_id, ring=20)

    # Append 15 entries first (no truncation yet), then 10 more (truncates 5).
    r1 = admin_client.post(
        "/api/v1/internal/append-log",
        json={
            "module_id": mod_id,
            "lines": [{"message": f"l{i}"} for i in range(15)],
        },
        headers=internal_headers(agent_id, secret, idempotency_key="trim-a"),
    )
    assert r1.json()["buffer_size"] == 15
    assert "truncated_count" not in r1.json()

    r2 = admin_client.post(
        "/api/v1/internal/append-log",
        json={
            "module_id": mod_id,
            "lines": [{"message": f"l{i}"} for i in range(15, 25)],
        },
        headers=internal_headers(agent_id, secret, idempotency_key="trim-b"),
    )
    body = r2.json()
    assert body["buffer_size"] == 20
    assert body["truncated_count"] == 5

    # Final state: only the last 20 (l5..l24).
    fetched = admin_client.get(f"/api/v1/modules/{mod_id}")
    msgs = [e["message"] for e in fetched.json()["data"]["entries"]]
    assert msgs == [f"l{i}" for i in range(5, 25)]


def test_append_log_rejects_wrong_module_type(admin_client: TestClient) -> None:
    agent_id, _ = register_agent(admin_client, name="log-wrong-type")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    mod_resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "markdown",
            "page_id": page_id,
            "data": {"body": "not a log"},
            "config": {},
            "owner_kind": "agent",
            "owner_id": agent_id,
        },
    )
    mod_id = mod_resp.json()["id"]
    resp = admin_client.post(
        "/api/v1/internal/append-log",
        json={"module_id": mod_id, "lines": [{"message": "x"}]},
        headers=internal_headers(agent_id, secret, idempotency_key="wt-1"),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "module.wrong_type"


def test_append_log_non_owner_goes_to_pending(admin_client: TestClient) -> None:
    """The owner_scope=self rule does NOT match a non-owner; falls back to the
    broader prompt rule."""
    owner_id, _ = register_agent(admin_client, name="owner-stream")
    other_id, _ = register_agent(admin_client, name="other-stream")
    secret = get_service_secret()
    page_id = home_page_id(admin_client)
    mod_id = _new_log_stream(admin_client, page_id=page_id, agent_id=owner_id)

    resp = admin_client.post(
        "/api/v1/internal/append-log",
        json={"module_id": mod_id, "lines": [{"message": "interloper"}]},
        headers=internal_headers(other_id, secret, idempotency_key="other-1"),
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"
