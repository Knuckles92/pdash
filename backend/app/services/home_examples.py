"""Clear and redeploy the canonical default Home example modules.

Single source of truth for the layout lives in :mod:`app.seed_home`; this
service applies that data through the normal ORM + SSE paths used by admin
module CRUD.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import modules as module_registry
from ..events.publish import publish_after_commit
from ..ids import new_id
from ..models import Module, utcnow_iso
from ..seed_home import SEED_VERSION, home_example_modules
from ..services.audit import write_event

DEFAULT_EXAMPLE_PERMISSIONS = {
    "pdash_default_example": True,
    "seed_version": SEED_VERSION,
}


def _module_event_summary(row: Module) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "page_id": row.page_id,
        "position": row.position,
        "version": row.version,
        "updated_at": row.updated_at,
        "owner_kind": row.owner_kind,
        "owner_id": row.owner_id,
    }


def is_default_example(module: Module) -> bool:
    permissions = json.loads(module.permissions or "{}")
    return permissions.get("pdash_default_example") is True


async def _default_example_modules(session: AsyncSession, page_id: str) -> list[Module]:
    rows = (
        await session.execute(
            select(Module).where(Module.page_id == page_id, Module.deleted_at.is_(None))
        )
    ).scalars().all()
    return [row for row in rows if is_default_example(row)]


async def count_default_examples(session: AsyncSession, page_id: str) -> int:
    return len(await _default_example_modules(session, page_id))


async def clear_default_examples(session: AsyncSession, page_id: str) -> int:
    """Soft-delete all default-example modules on ``page_id``. Returns count cleared."""
    rows = await _default_example_modules(session, page_id)
    if not rows:
        return 0

    now = utcnow_iso()
    for row in rows:
        row.deleted_at = now
        row.version += 1
        row.updated_at = now
        row.last_updated_by = "user:admin"
        publish_after_commit(
            session, f"page:{page_id}", "module_removed", {"module_id": row.id}
        )
        publish_after_commit(
            session, f"module:{row.id}", "module_removed", {"module_id": row.id}
        )

    await session.flush()
    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="clear_default_examples",
        target_kind="page",
        target_id=page_id,
        outcome="applied",
        payload_summary={"count": len(rows)},
    )
    return len(rows)


async def deploy_default_examples(session: AsyncSession, page_id: str) -> int:
    """Replace default-example modules on ``page_id`` with the canonical seed layout."""
    await clear_default_examples(session, page_id)

    now_dt = datetime.now(UTC)
    now = utcnow_iso()
    specs = home_example_modules(now_dt)
    permissions_json = json.dumps(DEFAULT_EXAMPLE_PERMISSIONS)

    for i, spec in enumerate(specs):
        clean_data = module_registry.validate_data(spec["type"], spec["data"])
        clean_config = module_registry.validate_config(spec["type"], spec["config"])
        mod_id = new_id("mod")
        row = Module(
            id=mod_id,
            type=spec["type"],
            title=spec["title"],
            owner_kind="user",
            owner_id="admin",
            page_id=page_id,
            position=i,
            grid=json.dumps({"colspan": spec.get("colspan", 1)}),
            permissions=permissions_json,
            data=json.dumps(clean_data),
            config=json.dumps(clean_config),
            schema_version=1,
            version=1,
            created_at=now,
            updated_at=now,
            last_updated_by="user:admin",
        )
        session.add(row)
        await session.flush()
        summary = _module_event_summary(row)
        publish_after_commit(
            session, f"page:{page_id}", "module_added", {"module": summary}
        )
        publish_after_commit(
            session, f"module:{mod_id}", "module_added", {"module": summary}
        )

    await write_event(
        session,
        actor_kind="user",
        actor_id="admin",
        action_type="deploy_default_examples",
        target_kind="page",
        target_id=page_id,
        outcome="applied",
        payload_summary={"count": len(specs)},
    )
    return len(specs)
