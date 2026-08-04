import type { ModuleType } from "./types";

/** Human-readable labels for module type pickers (rules, add-module, etc.). */
export const MODULE_TYPE_LABELS: Record<ModuleType, string> = {
  markdown: "Markdown",
  key_value: "Key / Value",
  table: "Table",
  link_list: "Link list",
  timeseries: "Timeseries (chart)",
  log_stream: "Log stream",
  iframe: "Iframe",
  notification: "Notification",
  action_button: "Action button",
  file: "File",
  sticky_note: "Sticky note",
  progress: "Progress bars",
  html: "HTML (canvas)",
};

export const MODULE_TYPE_DESCRIPTIONS: Record<ModuleType, string> = {
  markdown: "Sanitized markdown block. Great for notes and instructions.",
  key_value: "List of label → value pairs with severity chips.",
  table: "Columnar data with severity / link / action cells.",
  link_list: "Bookmark-style list, grid, or chips.",
  timeseries: "Line / bar / area chart with up to 6 series.",
  log_stream: "Append-only log view with severity + source.",
  iframe: "Embed an allowlisted external page (Grafana, etc.).",
  notification: "Banner card with optional action or pin-to-top.",
  action_button: "Button that fires a configured action_target.",
  file: "Show a registered image inline or a file as a download card.",
  sticky_note: "A note for a corkboard page — title, markdown body, and checklists. Agents can leave you notes here.",
  progress: "A list of named progress bars (current / target) with severity colors. Goal and quota tracking.",
  html: "A full agent-authored HTML document in a sandboxed iframe. Powers canvas pages; also embeddable as a grid tile.",
};

export function isKnownModuleType(value: string): value is ModuleType {
  return value in MODULE_TYPE_LABELS;
}
