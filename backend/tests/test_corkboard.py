"""Corkboard page type + sticky_note module type (board notes).

Locks in the two surfaces (the ``corkboard`` page type and the ``sticky_note``
type), the note's rich content fields (title / markdown / checklist / pinned),
and that the module ``grid`` JSON blob round-trips as an opaque value. The board
orders notes by pinned-then-recency; it no longer reads any board position out of
``grid`` (free-form ``{x,y,rotation}`` positioning was removed in the redesign).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _corkboard_page_id(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/pages",
        json={"slug": "board", "name": "Corkboard", "type": "corkboard"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["type"] == "corkboard"
    return resp.json()["id"]


def test_create_corkboard_page(admin_client: TestClient) -> None:
    page_id = _corkboard_page_id(admin_client)
    resp = admin_client.get(f"/api/v1/pages/{page_id}")
    assert resp.status_code == 200
    assert resp.json()["type"] == "corkboard"


def test_sticky_note_grid_blob_round_trips(admin_client: TestClient) -> None:
    # `grid` is an opaque JSON blob the modules API stores verbatim (normal pages
    # use it for {colspan}); the corkboard ignores it for layout. Lock in the
    # passthrough on create + patch — not any board-position semantics.
    page_id = _corkboard_page_id(admin_client)

    create = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "sticky_note",
            "page_id": page_id,
            "data": {"text": "remember the milk"},
            "config": {"color": "pink", "pin_style": "tape"},
            "grid": {"colspan": 2},
        },
    )
    assert create.status_code == 201, create.text
    mod = create.json()
    mod_id = mod["id"]
    assert mod["type"] == "sticky_note"
    assert mod["grid"] == {"colspan": 2}
    assert mod["data"]["text"] == "remember the milk"
    assert mod["config"]["color"] == "pink"

    patch = admin_client.patch(
        f"/api/v1/modules/{mod_id}",
        json={"grid": {"colspan": 3}},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["grid"] == {"colspan": 3}

    got = admin_client.get(f"/api/v1/modules/{mod_id}")
    assert got.status_code == 200
    assert got.json()["grid"] == {"colspan": 3}


def test_sticky_note_rejects_unknown_color(admin_client: TestClient) -> None:
    page_id = _corkboard_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "sticky_note",
            "page_id": page_id,
            "data": {"text": "x"},
            "config": {"color": "chartreuse"},
        },
    )
    assert resp.status_code >= 400


def test_sticky_note_rich_fields_round_trip(admin_client: TestClient) -> None:
    page_id = _corkboard_page_id(admin_client)
    create = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "sticky_note",
            "page_id": page_id,
            "data": {
                "title": "Groceries",
                "text": "don't forget **milk**",
                "pinned": True,
                "items": [
                    {"text": "eggs", "done": False},
                    {"text": "bread", "done": True},
                ],
            },
            "config": {"color": "green"},
        },
    )
    assert create.status_code == 201, create.text
    data = create.json()["data"]
    assert data["title"] == "Groceries"
    assert data["text"] == "don't forget **milk**"
    assert data["pinned"] is True
    assert data["items"] == [
        {"text": "eggs", "done": False},
        {"text": "bread", "done": True},
    ]
    # Legible sans is the new default font (no more handwriting-by-default).
    assert create.json()["config"]["font"] == "normal"


def test_sticky_note_checklist_item_rejects_extra_key(admin_client: TestClient) -> None:
    page_id = _corkboard_page_id(admin_client)
    resp = admin_client.post(
        "/api/v1/modules",
        json={
            "type": "sticky_note",
            "page_id": page_id,
            "data": {"items": [{"text": "x", "done": False, "nope": 1}]},
        },
    )
    assert resp.status_code >= 400
