/**
 * TS shapes mirroring backend/app/modules/*.py for the four Phase-2 module
 * types. Hand-written intentionally (per the plan) — schema-driven codegen is
 * deferred.
 */

import type { ModuleAppearance } from "./appearance";

export type Severity = "info" | "success" | "warning" | "error" | "muted";
export type IsoTimestamp = string;
export type IconName = string;

// ---- markdown ---------------------------------------------------------------
export type MarkdownData = {
  body: string;
  rendered_at?: IsoTimestamp | null;
};
export type MarkdownConfig = {
  collapsed_by_default?: boolean;
  max_height_px?: number;
  callout_severity?: Severity | null;
  show_rendered_at?: boolean;
  appearance?: ModuleAppearance;
};

// ---- key_value --------------------------------------------------------------
export type KeyValueField = {
  key: string;
  value: string | number | boolean | null;
  severity?: Severity | null;
  icon?: IconName | null;
  unit?: string | null;
  hint?: string | null;
};
export type KeyValueData = {
  fields: KeyValueField[];
  updated_at?: IsoTimestamp | null;
};
export type KeyValueLayout = "stacked" | "two-column" | "inline-chips";
export type KeyValueConfig = {
  layout?: KeyValueLayout;
  show_icons?: boolean;
  value_format?: "auto" | "monospace" | "humanize-number" | "humanize-bytes";
  show_updated_at?: boolean;
  appearance?: ModuleAppearance;
};

// ---- table ------------------------------------------------------------------
export type TableColType =
  | "text"
  | "number"
  | "timestamp"
  | "severity"
  | "icon"
  | "link"
  | "action";

export type TableColumn = {
  id: string;
  label: string;
  type: TableColType;
  align?: "left" | "center" | "right" | null;
  hide_on_mobile?: boolean;
};

export type TableCellRich = {
  text?: string;
  href?: string;
  icon?: IconName;
  severity?: Severity;
  action_target_id?: string;
  confirm?: boolean;
};

export type TableCell = string | number | boolean | null | TableCellRich;

export type TableRow = {
  row_id?: string | null;
  severity?: Severity | null;
  cells: Record<string, TableCell>;
};

export type TableData = {
  columns: TableColumn[];
  rows: TableRow[];
  updated_at?: IsoTimestamp | null;
};

export type TableConfig = {
  empty_message?: string | null;
  row_density?: "compact" | "normal" | "comfortable";
  mobile_layout?: "scroll" | "card-stack";
  default_sort?: Record<string, unknown> | null;
  appearance?: ModuleAppearance;
};

// ---- link_list --------------------------------------------------------------
export type LinkItem = {
  label: string;
  href: string;
  description?: string | null;
  icon?: IconName | null;
  severity?: Severity | null;
  external?: boolean | null;
};
export type LinkListData = {
  links: LinkItem[];
  updated_at?: IsoTimestamp | null;
};
export type LinkListLayout = "list" | "grid" | "chips";
export type LinkListConfig = {
  layout?: LinkListLayout;
  show_descriptions?: boolean;
  show_icons?: boolean;
  open_in_new_tab?: boolean;
  appearance?: ModuleAppearance;
};

// ---- timeseries ------------------------------------------------------------
export type TimeseriesPoint = {
  t: IsoTimestamp;
  v: number | null;
};
export type TimeseriesSeries = {
  id: string;
  label: string;
  color_token?: string | null;
  points: TimeseriesPoint[];
};
export type TimeseriesData = {
  series: TimeseriesSeries[];
  window_start?: IsoTimestamp | null;
  window_end?: IsoTimestamp | null;
};
export type TimeseriesChartType = "line" | "bar" | "area";
export type TimeseriesYAxisFormat = "auto" | "percent" | "bytes" | "duration_ms";
export type TimeseriesYAxis = {
  label?: string | null;
  min?: number | null;
  max?: number | null;
  unit?: string | null;
  format?: TimeseriesYAxisFormat;
};
export type TimeseriesXAxis = {
  label?: string | null;
};
export type TimeseriesConfig = {
  chart_type?: TimeseriesChartType;
  y_axis?: TimeseriesYAxis;
  x_axis?: TimeseriesXAxis;
  show_legend?: boolean;
  height_px?: number;
  appearance?: ModuleAppearance;
};

// ---- log_stream ------------------------------------------------------------
export type LogEntry = {
  t: IsoTimestamp;
  message: string;
  severity?: Severity | null;
  source?: string | null;
  icon?: IconName | null;
};
export type LogStreamData = {
  entries: LogEntry[];
  last_appended_at?: IsoTimestamp | null;
};
export type LogStreamOrder = "newest-first" | "oldest-first";
export type LogStreamConfig = {
  ring_buffer_size?: number;
  order?: LogStreamOrder;
  default_filter_severity?: Severity | null;
  show_source?: boolean;
  monospace?: boolean;
  appearance?: ModuleAppearance;
};

// ---- iframe ----------------------------------------------------------------
export type IframeSandboxFlag =
  | "allow-scripts"
  | "allow-same-origin"
  | "allow-forms"
  | "allow-popups";
export type IframeReferrerPolicy =
  | "no-referrer"
  | "no-referrer-when-downgrade"
  | "origin"
  | "origin-when-cross-origin"
  | "same-origin"
  | "strict-origin"
  | "strict-origin-when-cross-origin"
  | "unsafe-url";
export type IframeData = {
  src: string;
  title?: string | null;
};
export type IframeConfig = {
  height_px?: number;
  mobile_height_px?: number;
  sandbox?: IframeSandboxFlag[];
  referrer_policy?: IframeReferrerPolicy;
  show_chrome?: boolean;
  appearance?: ModuleAppearance;
};

// ---- html -------------------------------------------------------------------
export type HtmlData = {
  html: string;
  title?: string | null;
};
export type HtmlConfig = {
  height_px?: number;
  mobile_height_px?: number;
  appearance?: ModuleAppearance;
};

// ---- notification ----------------------------------------------------------
export type NotificationAction = {
  label: string;
  href?: string | null;
  action_target_id?: string | null;
};
export type NotificationData = {
  message: string;
  severity: Severity;
  created_at: IsoTimestamp;
  expires_at?: IsoTimestamp | null;
  dismissed_at?: IsoTimestamp | null;
  action?: NotificationAction | null;
  icon?: IconName | null;
};
export type NotificationConfig = {
  dismissible?: boolean;
  auto_dismiss_seconds?: number | null;
  pin_to_top?: boolean;
  sound?: boolean;
  appearance?: ModuleAppearance;
};

// ---- action_button ---------------------------------------------------------
export type ActionButtonLastResult = {
  fired_at: IsoTimestamp;
  ok: boolean;
  message?: string | null;
  details?: Record<string, unknown> | null;
};
export type ActionButtonData = {
  label: string;
  action_target_id: string;
  icon?: IconName | null;
  severity?: Severity | null;
  disabled?: boolean;
  last_result?: ActionButtonLastResult | null;
};
export type ActionButtonStyle = "primary" | "secondary" | "destructive";
export type ActionButtonConfig = {
  confirm?: boolean;
  confirm_text?: string | null;
  cooldown_seconds?: number;
  style?: ActionButtonStyle;
  show_last_result?: boolean;
  appearance?: ModuleAppearance;
};

// ---- file ------------------------------------------------------------------
export type FileKind = "image" | "document";
export type FileFit = "contain" | "cover";
export type FileData = {
  file_id: string;
  kind: FileKind;
  display_name: string;
  mime?: string | null;
  alt?: string | null;
  size_bytes?: number | null;
  registered_at?: IsoTimestamp | null;
};
export type FileConfig = {
  max_height_px?: number;
  fit?: FileFit;
  show_download?: boolean;
  show_filename?: boolean;
  appearance?: ModuleAppearance;
};

// ---- sticky_note ------------------------------------------------------------
export type NoteColor = "yellow" | "pink" | "blue" | "green" | "orange" | "purple" | "white";
export type PinStyle = "pin" | "tape" | "none";
export type NoteFont = "hand" | "normal";
export type ChecklistItem = {
  text: string;
  done: boolean;
};
export type StickyNoteData = {
  title?: string;
  text?: string;
  items?: ChecklistItem[];
  done?: boolean;
  pinned?: boolean;
  created_at?: IsoTimestamp | null;
};
export type StickyNoteConfig = {
  color?: NoteColor;
  pin_style?: PinStyle;
  font?: NoteFont;
  appearance?: ModuleAppearance;
};

// ---- progress ---------------------------------------------------------------
export type ProgressBar = {
  id?: string;
  label: string;
  current?: number;
  target: number;
  unit?: string | null;
  severity?: Severity | null;
  icon?: IconName | null;
  hint?: string | null;
};
export type ProgressData = {
  bars: ProgressBar[];
  updated_at?: IsoTimestamp | null;
};
export type ProgressDensity = "compact" | "normal";
export type ProgressSort = "as-is" | "percent-asc" | "percent-desc" | "label";
export type ProgressConfig = {
  show_values?: boolean;
  show_percent?: boolean;
  density?: ProgressDensity;
  sort?: ProgressSort;
  empty_message?: string | null;
  appearance?: ModuleAppearance;
};

// ---- registry --------------------------------------------------------------
export const PHASE_2_TYPES = ["markdown", "key_value", "table", "link_list"] as const;
export type Phase2Type = (typeof PHASE_2_TYPES)[number];

export function isPhase2Type(s: string): s is Phase2Type {
  return (PHASE_2_TYPES as readonly string[]).includes(s);
}

export const PHASE_4_TYPES = [
  "timeseries",
  "log_stream",
  "iframe",
  "notification",
  "action_button",
] as const;
export type Phase4Type = (typeof PHASE_4_TYPES)[number];

export function isPhase4Type(s: string): s is Phase4Type {
  return (PHASE_4_TYPES as readonly string[]).includes(s);
}

export const PHASE_5_TYPES = ["file"] as const;
export type Phase5Type = (typeof PHASE_5_TYPES)[number];

export function isPhase5Type(s: string): s is Phase5Type {
  return (PHASE_5_TYPES as readonly string[]).includes(s);
}

export const CORKBOARD_TYPES = ["sticky_note"] as const;
export type CorkboardType = (typeof CORKBOARD_TYPES)[number];

export function isCorkboardType(s: string): s is CorkboardType {
  return (CORKBOARD_TYPES as readonly string[]).includes(s);
}

export const PROGRESS_TYPES = ["progress"] as const;
export type ProgressType = (typeof PROGRESS_TYPES)[number];

export function isProgressType(s: string): s is ProgressType {
  return (PROGRESS_TYPES as readonly string[]).includes(s);
}

export const CANVAS_TYPES = ["html"] as const;
export type CanvasType = (typeof CANVAS_TYPES)[number];

export function isCanvasType(s: string): s is CanvasType {
  return (CANVAS_TYPES as readonly string[]).includes(s);
}

export const ALL_MODULE_TYPES = [
  ...PHASE_2_TYPES,
  ...PHASE_4_TYPES,
  ...PHASE_5_TYPES,
  ...CORKBOARD_TYPES,
  ...PROGRESS_TYPES,
  ...CANVAS_TYPES,
] as const;
export type ModuleType = (typeof ALL_MODULE_TYPES)[number];
