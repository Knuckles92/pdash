"""Module schema endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..auth.deps import CurrentUser, require_session
from ..errors import not_found
from ..modules import MODULE_TYPES, schema_for

router = APIRouter(prefix="/api/v1/module-schemas", tags=["module-schemas"])


@router.get("")
async def list_schemas(_: Annotated[CurrentUser, Depends(require_session)]) -> dict:
    return {
        "types": list(MODULE_TYPES),
        "schemas": [schema_for(t) for t in MODULE_TYPES],
    }


@router.get("/{module_type}")
async def get_schema(
    module_type: str,
    _: Annotated[CurrentUser, Depends(require_session)],
) -> dict:
    try:
        return schema_for(module_type)
    except KeyError as exc:
        raise not_found("module_schema.not_found", f"module type {module_type!r}") from exc
