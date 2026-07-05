"""Module type registry.

One file per type — each exports `Data` and `Config` Pydantic models.
The registry maps the type string to those models so the schema endpoint
can return JSON Schema for either.
"""

from __future__ import annotations

from typing import Any

from . import (
    action_button,
    file,
    html,
    iframe,
    key_value,
    link_list,
    log_stream,
    markdown,
    notification,
    progress,
    sticky_note,
    table,
    timeseries,
)

MODULE_TYPES: tuple[str, ...] = (
    "markdown",
    "key_value",
    "table",
    "timeseries",
    "log_stream",
    "link_list",
    "iframe",
    "action_button",
    "notification",
    "file",
    "sticky_note",
    "progress",
    "html",
)

REGISTRY: dict[str, dict[str, Any]] = {
    "markdown": {"data": markdown.Data, "config": markdown.Config},
    "key_value": {"data": key_value.Data, "config": key_value.Config},
    "table": {"data": table.Data, "config": table.Config},
    "timeseries": {"data": timeseries.Data, "config": timeseries.Config},
    "log_stream": {"data": log_stream.Data, "config": log_stream.Config},
    "link_list": {"data": link_list.Data, "config": link_list.Config},
    "iframe": {"data": iframe.Data, "config": iframe.Config},
    "action_button": {"data": action_button.Data, "config": action_button.Config},
    "notification": {"data": notification.Data, "config": notification.Config},
    "file": {"data": file.Data, "config": file.Config},
    "sticky_note": {"data": sticky_note.Data, "config": sticky_note.Config},
    "progress": {"data": progress.Data, "config": progress.Config},
    "html": {"data": html.Data, "config": html.Config},
}


def schema_for(module_type: str) -> dict[str, Any]:
    """Return `{type, data, config}` JSON-Schema dict for the given module type."""
    if module_type not in REGISTRY:
        raise KeyError(module_type)
    entry = REGISTRY[module_type]
    data_schema = entry["data"].model_json_schema()
    config_schema = entry["config"].model_json_schema()
    return {
        "type": module_type,
        "data": data_schema,
        "config": config_schema,
        # data_schema/config_schema are compatibility aliases consumed by the frontend SchemaForm.
        "data_schema": data_schema,
        "config_schema": config_schema,
    }


def validate_data(module_type: str, data: Any) -> dict[str, Any]:
    if module_type not in REGISTRY:
        raise KeyError(module_type)
    model = REGISTRY[module_type]["data"]
    return model.model_validate(data).model_dump(mode="json", exclude_none=True)


def validate_config(module_type: str, config: Any) -> dict[str, Any]:
    if module_type not in REGISTRY:
        raise KeyError(module_type)
    model = REGISTRY[module_type]["config"]
    return model.model_validate(config).model_dump(mode="json", exclude_none=True)


__all__ = ["MODULE_TYPES", "REGISTRY", "schema_for", "validate_data", "validate_config"]
