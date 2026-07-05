/**
 * Map agent-supplied color tokens (e.g. `sky`, `amber`, `emerald`) to concrete
 * hex strings sourced from Tailwind's palette. We pick mid-range hues that
 * work in both light and dark mode against the muted-foreground/foreground
 * color the rest of the dashboard uses.
 *
 * If a token isn't in the map we fall back to a stable hash so repeated
 * unknown tokens still get distinct colors. Agents should prefer the listed
 * names — they're the ones with good contrast and they round-trip cleanly
 * back into icons + chips elsewhere in the UI.
 */

export const COLOR_TOKENS = [
  "sky",
  "blue",
  "indigo",
  "violet",
  "purple",
  "fuchsia",
  "pink",
  "rose",
  "red",
  "orange",
  "amber",
  "yellow",
  "lime",
  "green",
  "emerald",
  "teal",
  "cyan",
  "gray",
  "slate",
  "zinc",
] as const;

export type ColorToken = (typeof COLOR_TOKENS)[number];

export const COLOR_LABELS: Record<ColorToken, string> = {
  sky: "Sky",
  blue: "Blue",
  indigo: "Indigo",
  violet: "Violet",
  purple: "Purple",
  fuchsia: "Fuchsia",
  pink: "Pink",
  rose: "Rose",
  red: "Red",
  orange: "Orange",
  amber: "Amber",
  yellow: "Yellow",
  lime: "Lime",
  green: "Green",
  emerald: "Emerald",
  teal: "Teal",
  cyan: "Cyan",
  gray: "Gray",
  slate: "Slate",
  zinc: "Zinc",
};

const PALETTE: Record<ColorToken, string> = {
  sky: "#0ea5e9",
  blue: "#3b82f6",
  indigo: "#6366f1",
  violet: "#8b5cf6",
  purple: "#a855f7",
  fuchsia: "#d946ef",
  pink: "#ec4899",
  rose: "#f43f5e",
  red: "#ef4444",
  orange: "#f97316",
  amber: "#f59e0b",
  yellow: "#eab308",
  lime: "#84cc16",
  green: "#22c55e",
  emerald: "#10b981",
  teal: "#14b8a6",
  cyan: "#06b6d4",
  gray: "#71717a",
  slate: "#64748b",
  zinc: "#71717a",
};

const FALLBACK = [
  "#0ea5e9",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#a855f7",
  "#14b8a6",
];

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash;
}

export function tokenToHex(token: string | null | undefined, fallbackIndex = 0): string {
  if (!token) {
    return FALLBACK[fallbackIndex % FALLBACK.length] ?? FALLBACK[0]!;
  }
  const lower = token.toLowerCase();
  if (/^#[0-9a-f]{6}$/i.test(lower)) return lower;
  if (lower in PALETTE) return PALETTE[lower as ColorToken]!;
  return FALLBACK[hashString(lower) % FALLBACK.length] ?? FALLBACK[0]!;
}

export function paletteHex(index: number): string {
  return FALLBACK[index % FALLBACK.length] ?? FALLBACK[0]!;
}

export function colorToRgba(color: string, alpha: number): string {
  const hex = tokenToHex(color).replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function readableTextOn(color: string): "#0a0a0a" | "#ffffff" {
  const hex = tokenToHex(color).replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16) / 255;
  const g = parseInt(hex.slice(2, 4), 16) / 255;
  const b = parseInt(hex.slice(4, 6), 16) / 255;
  const linear = [r, g, b].map((channel) =>
    channel <= 0.03928
      ? channel / 12.92
      : Math.pow((channel + 0.055) / 1.055, 2.4),
  );
  const luminance =
    0.2126 * (linear[0] ?? 0) +
    0.7152 * (linear[1] ?? 0) +
    0.0722 * (linear[2] ?? 0);
  return luminance > 0.55 ? "#0a0a0a" : "#ffffff";
}
