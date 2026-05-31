import type { CSSProperties } from "react";

import { cn } from "@/lib/cn";
import {
  COLOR_LABELS,
  COLOR_TOKENS,
  colorToRgba,
  tokenToHex,
  readableTextOn,
  type ColorToken,
} from "@/lib/modules/color_token";

export type ModuleAppearanceTheme = "default" | "tinted" | "solid" | "outline";

export type ModuleAppearance = {
  theme?: ModuleAppearanceTheme;
  color?: ColorToken | null;
};

export const MODULE_THEME_OPTIONS: Array<{
  value: ModuleAppearanceTheme;
  label: string;
}> = [
  { value: "default", label: "Default" },
  { value: "tinted", label: "Tinted" },
  { value: "solid", label: "Solid" },
  { value: "outline", label: "Outline" },
];

export const MODULE_COLOR_OPTIONS = COLOR_TOKENS.map((value) => ({
  value,
  label: COLOR_LABELS[value],
  hex: tokenToHex(value),
}));

const THEME_VALUES = new Set<ModuleAppearanceTheme>(
  MODULE_THEME_OPTIONS.map((option) => option.value),
);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function normalizeTheme(value: unknown): ModuleAppearanceTheme {
  return typeof value === "string" && THEME_VALUES.has(value as ModuleAppearanceTheme)
    ? (value as ModuleAppearanceTheme)
    : "default";
}

function normalizeColor(value: unknown): ColorToken | null {
  return typeof value === "string" && COLOR_TOKENS.includes(value as ColorToken)
    ? (value as ColorToken)
    : null;
}

export function moduleAppearanceFromConfig(
  config: Record<string, unknown> | null | undefined,
): Required<ModuleAppearance> {
  const appearance = isRecord(config?.appearance) ? config.appearance : {};
  return {
    theme: normalizeTheme(appearance.theme),
    color: normalizeColor(appearance.color),
  };
}

export function appearanceVars(appearance: Required<ModuleAppearance>): CSSProperties {
  const color = appearance.color ?? "blue";
  return {
    "--module-accent": tokenToHex(color),
    "--module-accent-fg": readableTextOn(color),
    "--module-accent-soft": colorToRgba(color, 0.12),
    "--module-accent-wash": colorToRgba(color, 0.055),
    "--module-accent-border": colorToRgba(color, 0.35),
  } as CSSProperties;
}

// Accent top-bar: a colored inset bar plus matching border, shared by the
// `tinted` theme and the bare-`color` fallback.
const ACCENT_TOP_BAR =
  "border-[var(--module-accent-border)] shadow-[inset_0_3px_0_var(--module-accent)]";

export function appearanceCardClass(appearance: Required<ModuleAppearance>): string {
  if (appearance.theme === "solid") {
    return "border-[var(--module-accent-border)]";
  }
  if (appearance.theme === "tinted") {
    return cn(ACCENT_TOP_BAR, "bg-[var(--module-accent-wash)]");
  }
  if (appearance.theme === "outline") {
    return "border-[var(--module-accent)] shadow-[inset_0_0_0_1px_var(--module-accent-border)]";
  }
  if (appearance.color) {
    return ACCENT_TOP_BAR;
  }
  return "";
}

export function appearanceHeaderClass(appearance: Required<ModuleAppearance>): string {
  if (appearance.theme === "solid") {
    return "border-[var(--module-accent)] bg-[var(--module-accent)] text-[var(--module-accent-fg)]";
  }
  if (appearance.theme === "tinted") {
    return "border-[var(--module-accent-border)] bg-[var(--module-accent-soft)]";
  }
  if (appearance.theme === "outline" || appearance.color) {
    return "border-[var(--module-accent-border)]";
  }
  return "";
}
