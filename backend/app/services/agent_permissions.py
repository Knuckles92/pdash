"""Typed overlay on ``agents.permissions``. Empty keys mean unrestricted."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..errors import forbidden


class AgentPermissions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowed_module_types: list[str] | None = None
    allowed_page_ids: list[str] | None = None
    can_fire_action: bool = True


def parse_permissions(raw: str | dict[str, Any] | None) -> AgentPermissions:
    if raw is None or raw == "":
        return AgentPermissions()
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return AgentPermissions()
    else:
        data = raw
    if not isinstance(data, dict):
        return AgentPermissions()
    return AgentPermissions.model_validate(data)


def enforce_permissions(
    raw: str | dict[str, Any] | None,
    *,
    module_type: str | None = None,
    page_id: str | None = None,
    fire: bool = False,
) -> AgentPermissions:
    perms = parse_permissions(raw)
    if (
        perms.allowed_module_types is not None
        and module_type is not None
        and module_type not in perms.allowed_module_types
    ):
        raise forbidden(
            "agent.permission_denied",
            f"agent is not allowed to use module type {module_type}",
        )
    if (
        perms.allowed_page_ids is not None
        and page_id is not None
        and page_id not in perms.allowed_page_ids
    ):
        raise forbidden(
            "agent.permission_denied",
            f"agent is not allowed to write to page {page_id}",
        )
    if fire and not perms.can_fire_action:
        raise forbidden(
            "agent.permission_denied",
            "agent is not allowed to fire actions",
        )
    return perms
