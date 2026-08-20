"""Risk classifier: map an update patch onto an action_type.

The engine still matches on action_type. This module is the risk grain —
capability-shaped field changes become ``update_module_capability`` (default
prompt) instead of riding along on ``update_module_data`` / ``update_module_config``.
"""

from __future__ import annotations

from typing import Any

from ..modules._common import deep_merge

CAPABILITY_ACTION = "update_module_capability"

_SANDBOX_RANK = {
    "allow-same-origin": 4,
    "allow-scripts": 3,
    "allow-forms": 2,
    "allow-popups": 1,
}


def classify_update(
    module_type: str,
    existing_data: dict[str, Any],
    existing_config: dict[str, Any],
    patch: dict[str, Any],
) -> str:
    """Pick the action_type for an update patch.

    Capability wins over content. Content (data) wins over cosmetic config.
    Meta (title/position/grid/page_id) is the remainder.
    """
    merged_data = (
        deep_merge(existing_data, patch["data"]) if "data" in patch else existing_data
    )
    merged_config = (
        deep_merge(existing_config, patch["config"])
        if "config" in patch
        else existing_config
    )
    if _is_capability(
        module_type, existing_data, existing_config, merged_data, merged_config
    ):
        return CAPABILITY_ACTION
    if "data" in patch:
        return "update_module_data"
    if "config" in patch:
        return "update_module_config"
    return "update_module_meta"


def _is_capability(
    module_type: str,
    old_data: dict[str, Any],
    old_config: dict[str, Any],
    new_data: dict[str, Any],
    new_config: dict[str, Any],
) -> bool:
    if module_type == "iframe":
        if _norm_url(old_data.get("src")) != _norm_url(new_data.get("src")):
            return True
        if _sandbox_loosens(old_config.get("sandbox"), new_config.get("sandbox")):
            return True
    elif module_type == "action_button":
        if old_data.get("action_target_id") != new_data.get("action_target_id"):
            return True
        if old_config.get("confirm") is True and new_config.get("confirm") is False:
            return True
    elif module_type == "table":
        if _columns_identity(old_data.get("columns")) != _columns_identity(
            new_data.get("columns")
        ):
            return True
    return False


def _norm_url(value: Any) -> str:
    if value is None:
        return ""
    return str(value).rstrip("/")


def _sandbox_loosens(old: Any, new: Any) -> bool:
    old_set = {str(f) for f in (old or [])}
    new_set = {str(f) for f in (new or [])}
    added = new_set - old_set
    if added:
        return True
    old_rank = sum(_SANDBOX_RANK.get(f, 0) for f in old_set)
    new_rank = sum(_SANDBOX_RANK.get(f, 0) for f in new_set)
    return new_rank > old_rank


def _columns_identity(columns: Any) -> list[tuple[Any, Any]]:
    if not isinstance(columns, list):
        return []
    out: list[tuple[Any, Any]] = []
    for col in columns:
        if isinstance(col, dict):
            out.append((col.get("id"), col.get("type")))
        else:
            out.append((col, None))
    return out



