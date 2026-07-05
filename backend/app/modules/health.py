"""Module health + dashboard render helpers (read-only, no DB access).

These power the agent-facing visibility endpoints (PLAN §6):

- :func:`validate_payload` — dry-run a module's data/config against its type's
  Pydantic schema and report structured per-field errors. This is the same
  validation the renderer implicitly relies on, so "would this module render?"
  reduces to "does its stored payload still validate?".
- :func:`render_status` — render_ok/errors for a single serialized module.
- :func:`order_modules` / :func:`layout_summary` — reconstruct the dashboard
  grid order + an ASCII sketch so an agent can "see" the layout without pixels.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from . import REGISTRY

# The dashboard grid is grid-cols-1 lg:grid-cols-2 xl:grid-cols-3, so a module's
# colspan is meaningful up to 3 columns (frontend/lib/modules/grid.ts).
GRID_COLUMNS = 3


def validate_payload(
    module_type: str, data: Any, config: Any
) -> dict[str, Any]:
    """Validate a module's ``data`` + ``config`` against its type schema.

    Side-effect-free. Returns ``{ok, type_known, errors}`` where each error is
    ``{section, loc, msg, type}`` (``section`` is ``"data"`` or ``"config"``).
    Unknown module types are reported as ``type_known=False`` rather than raised
    so the caller gets a uniform, actionable shape.
    """
    if module_type not in REGISTRY:
        return {
            "ok": False,
            "type_known": False,
            "errors": [
                {
                    "section": "type",
                    "loc": "type",
                    "msg": f"unknown module type: {module_type!r}",
                    "type": "unknown_type",
                }
            ],
        }

    errors: list[dict[str, Any]] = []
    for section, payload in (("data", data or {}), ("config", config or {})):
        model = REGISTRY[module_type][section]
        try:
            model.model_validate(payload)
        except ValidationError as exc:
            errors.extend(format_validation_error(section, exc))
        except Exception as exc:  # noqa: BLE001 — defensive: non-pydantic failure
            errors.append(
                {"section": section, "loc": section, "msg": str(exc), "type": "error"}
            )
    return {"ok": not errors, "type_known": True, "errors": errors}


def format_validation_error(
    section: str, exc: ValidationError
) -> list[dict[str, Any]]:
    """Flatten a pydantic ``ValidationError`` into ``{section, loc, msg, type}`` rows."""
    out: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ())) or section
        out.append(
            {
                "section": section,
                "loc": loc,
                "msg": err.get("msg", "invalid"),
                "type": err.get("type", "value_error"),
            }
        )
    return out


def render_status(module: dict[str, Any]) -> dict[str, Any]:
    """Compute ``{render_ok, type_known, errors}`` for a serialized module dict."""
    report = validate_payload(
        module.get("type", ""), module.get("data"), module.get("config")
    )
    return {
        "render_ok": report["ok"],
        "type_known": report["type_known"],
        "errors": report["errors"],
    }


def _colspan(module: dict[str, Any]) -> int:
    grid = module.get("grid") or {}
    value = grid.get("colspan")
    return value if value in (2, 3) else 1


def _pin_key(module: dict[str, Any]) -> int:
    # Mirrors frontend/components/page/PageGrid.tsx: pinned notifications float
    # to the top; everything else keeps its (position, created_at) order.
    if module.get("type") == "notification" and (module.get("config") or {}).get(
        "pin_to_top"
    ):
        return 0
    return 1


def order_modules(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return modules in display order.

    Expects ``modules`` already sorted by (position, created_at); applies a
    stable sort so pinned notifications float to the top, matching the frontend.
    """
    return sorted(modules, key=_pin_key)


def layout_summary(
    modules: list[dict[str, Any]], columns: int = GRID_COLUMNS
) -> dict[str, Any]:
    """Pack modules into a ``columns``-wide grid and render an ASCII sketch.

    Returns ``{columns, rows, ascii}``. ``rows`` is a list of rows, each a list
    of ``{id, title, type, colspan, render_ok}`` cells. The ASCII art draws each
    module as a box whose width reflects its colspan — a headless stand-in for a
    screenshot.
    """
    rows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0
    for module in modules:
        span = min(_colspan(module), columns)
        if used + span > columns and current:
            rows.append(current)
            current, used = [], 0
        current.append(
            {
                "id": module.get("id"),
                "title": module.get("title") or "(untitled)",
                "type": module.get("type"),
                "colspan": span,
                "render_ok": bool((module.get("health") or {}).get("render_ok", True)),
            }
        )
        used += span
    if current:
        rows.append(current)

    return {"columns": columns, "rows": rows, "ascii": _ascii_grid(rows)}


# Inner width of a single grid column in the ASCII sketch.
_CELL_INNER = 18


def _cell_width(colspan: int) -> int:
    # A wider cell absorbs the borders it spans over (each extra column adds its
    # inner width plus the "+" separator that no longer splits the cell).
    return _CELL_INNER * colspan + (colspan - 1)


def _fit(text: str, width: int) -> str:
    text = text if len(text) <= width else text[: max(0, width - 1)] + "…"
    return text.ljust(width)


def _ascii_grid(rows: list[list[dict[str, Any]]]) -> str:
    if not rows:
        return "(empty page — no modules)"
    lines: list[str] = []
    for row in rows:
        border = "+" + "+".join("-" * _cell_width(c["colspan"]) for c in row) + "+"
        titles = (
            "|"
            + "|".join(
                " " + _fit(c["title"], _cell_width(c["colspan"]) - 1) for c in row
            )
            + "|"
        )
        metas = (
            "|"
            + "|".join(
                " "
                + _fit(
                    f"{c['type']}{'' if c['render_ok'] else '  [ERROR]'}",
                    _cell_width(c["colspan"]) - 1,
                )
                for c in row
            )
            + "|"
        )
        lines.extend([border, titles, metas])
    # Close the final row.
    last = rows[-1]
    lines.append("+" + "+".join("-" * _cell_width(c["colspan"]) for c in last) + "+")
    return "\n".join(lines)


__all__ = [
    "GRID_COLUMNS",
    "format_validation_error",
    "layout_summary",
    "order_modules",
    "render_status",
    "validate_payload",
]
