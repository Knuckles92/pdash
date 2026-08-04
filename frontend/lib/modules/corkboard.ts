/**
 * Notes board: themes + palette helpers.
 *
 * A corkboard page renders its `sticky_note` modules as a tidy, gap-free masonry
 * of cards (pinned notes first, then newest). The *look* of that board — the
 * surface behind the cards and how each card is styled — is driven by a theme the
 * admin picks live; the choice is persisted client-side per board (localStorage).
 *
 * Notes are ordered pinned-first (`data.pinned`) then newest (`created_at`);
 * there is no free-positioning / rotation anymore.
 */

import type { CSSProperties } from "react";

import type { NoteColor } from "./types";

// ---- palettes ---------------------------------------------------------------

/** Saturated "paper" look per color — used by the Corkboard theme. */
export const NOTE_PAPER: Record<NoteColor, { base: string; edge: string; ink: string }> = {
  yellow: { base: "#fdf389", edge: "#f4df57", ink: "#4a3f00" },
  pink: { base: "#f9bdd2", edge: "#f193b3", ink: "#5a1733" },
  blue: { base: "#aed8f4", edge: "#7cbfee", ink: "#0b3a5a" },
  green: { base: "#bfe6a3", edge: "#98d674", ink: "#1f4012" },
  orange: { base: "#fbcf90", edge: "#f7b659", ink: "#5a3306" },
  purple: { base: "#d6bef1", edge: "#bd9be8", ink: "#341a57" },
  white: { base: "#fcfbf6", edge: "#ebe9dc", ink: "#2b2b2b" },
};

/** Soft, lightened tints with readable ink — used by the Pastel theme. */
const NOTE_PASTEL: Record<NoteColor, { base: string; ink: string }> = {
  yellow: { base: "#fdf7d6", ink: "#5c4d05" },
  pink: { base: "#fde0ea", ink: "#7c2348" },
  blue: { base: "#e1eefb", ink: "#0c3a59" },
  green: { base: "#e5f3db", ink: "#274619" },
  orange: { base: "#fde8d0", ink: "#6b3b0c" },
  purple: { base: "#ede2fb", ink: "#3e2470" },
  white: { base: "#fbfaf6", ink: "#2b2b2b" },
};

/** Vivid single-color accents — for bars / dots / strips on neutral cards. */
export const NOTE_ACCENT: Record<NoteColor, string> = {
  yellow: "#f59e0b",
  pink: "#ec4899",
  blue: "#3b82f6",
  green: "#22c55e",
  orange: "#f97316",
  purple: "#a855f7",
  white: "#94a3b8",
};

export const NOTE_COLOR_ORDER: NoteColor[] = [
  "yellow",
  "pink",
  "blue",
  "green",
  "orange",
  "purple",
  "white",
];

/** Swatch shown in the color picker (the dominant fill of the note in any theme). */
export function noteSwatch(color: NoteColor): string {
  return NOTE_PAPER[color].base;
}

// ---- cork texture -----------------------------------------------------------

// Grayscale fractal-noise tile → cork grain over the warm base. Self-contained
// (no asset/network), so it works on an offline Tailscale deployment.
const CORK_NOISE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.4'/%3E%3C/svg%3E\")";

// ---- themes -----------------------------------------------------------------

export type NoteAccentKind = "none" | "bar" | "dot" | "strip";

export type NoteVisual = {
  /** Tailwind classes for the card wrapper (includes padding + shape). */
  className: string;
  /** Inline styles for the card wrapper (bg / border / shadow / ink color). */
  style: CSSProperties;
  /** How the note's color is expressed on this theme's card. */
  accent: { kind: NoteAccentKind; color: string };
  /** Show a pushpin at the top of the card. */
  showPin: boolean;
  /** Draw faint ruled lines + a margin line behind the body (legal-pad look). */
  ruled: boolean;
};

export type NotesTheme = {
  id: NotesThemeId;
  label: string;
  /** One-line description for the picker. */
  blurb: string;
  /** Outer frame around the whole board (e.g. the wood frame). */
  frame: { className: string; style: CSSProperties };
  /** The surface the cards sit on (e.g. cork / soft board / nothing). */
  surface: { className: string; style: CSSProperties };
  /** Resolve a single note's card visuals from its color. */
  note: (color: NoteColor) => NoteVisual;
  /**
   * Whether this theme honors a note's `font: "hand"` opt-in. Only the Corkboard
   * theme does — everywhere else stays legible sans regardless of stored font, so
   * the default board is always readable.
   */
  allowHandFont: boolean;
};

export const NOTES_THEME_IDS = ["clean", "corkboard", "pastel", "minimal", "ruled"] as const;
export type NotesThemeId = (typeof NOTES_THEME_IDS)[number];

export function isNotesThemeId(value: unknown): value is NotesThemeId {
  return typeof value === "string" && (NOTES_THEME_IDS as readonly string[]).includes(value);
}

const NO_FRAME = { className: "", style: {} as CSSProperties };

export const NOTES_THEMES: Record<NotesThemeId, NotesTheme> = {
  clean: {
    id: "clean",
    label: "Clean",
    blurb: "Crisp neutral cards that match the dashboard, with a colored accent bar.",
    allowHandFont: false,
    frame: NO_FRAME,
    surface: { className: "", style: {} },
    note: (color) => ({
      className: "rounded-xl border p-3.5 shadow-sm",
      style: {
        backgroundColor: "var(--card)",
        borderColor: "var(--border)",
        color: "var(--fg)",
      },
      accent: { kind: "bar", color: NOTE_ACCENT[color] },
      showPin: false,
      ruled: false,
    }),
  },

  corkboard: {
    id: "corkboard",
    label: "Corkboard",
    blurb: "Warm cork board with pushpins — straightened and legible.",
    allowHandFont: true,
    frame: {
      className: "rounded-2xl p-2.5",
      style: {
        backgroundImage: "linear-gradient(180deg,#8a5a2b,#6f4420)",
        boxShadow: "inset 0 2px 6px rgba(255,255,255,0.18), 0 12px 34px -12px rgba(0,0,0,0.55)",
      },
    },
    surface: {
      className: "rounded-lg p-4",
      style: {
        backgroundColor: "#c79f63",
        backgroundImage: CORK_NOISE,
        backgroundSize: "180px 180px",
        boxShadow: "inset 0 0 70px rgba(0,0,0,0.28), inset 0 0 8px rgba(0,0,0,0.22)",
      },
    },
    note: (color) => {
      const paper = NOTE_PAPER[color];
      return {
        className: "rounded-md p-3.5",
        style: {
          backgroundColor: paper.base,
          backgroundImage: `linear-gradient(160deg, ${paper.base} 0%, ${paper.edge} 100%)`,
          color: paper.ink,
          boxShadow: "0 1px 1px rgba(0,0,0,0.10), 0 12px 20px -10px rgba(0,0,0,0.42)",
        },
        accent: { kind: "none", color: NOTE_ACCENT[color] },
        showPin: true,
        ruled: false,
      };
    },
  },

  pastel: {
    id: "pastel",
    label: "Pastel",
    blurb: "Soft colored paper on a warm board — gentle and easy on the eyes.",
    allowHandFont: false,
    frame: NO_FRAME,
    surface: {
      className: "rounded-2xl border p-4 sm:p-5",
      style: {
        backgroundImage: "linear-gradient(160deg,#faf7f0,#f1ebdf)",
        borderColor: "rgba(0,0,0,0.06)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.6), 0 1px 2px rgba(0,0,0,0.04)",
      },
    },
    note: (color) => {
      const p = NOTE_PASTEL[color];
      return {
        className: "rounded-xl p-3.5",
        style: {
          backgroundColor: p.base,
          color: p.ink,
          boxShadow: "0 1px 2px rgba(0,0,0,0.06), 0 8px 18px -12px rgba(0,0,0,0.28)",
        },
        accent: { kind: "none", color: NOTE_ACCENT[color] },
        showPin: false,
        ruled: false,
      };
    },
  },

  minimal: {
    id: "minimal",
    label: "Minimal",
    blurb: "Flat hairline cards with a tiny color dot — quiet and dense.",
    allowHandFont: false,
    frame: NO_FRAME,
    surface: { className: "", style: {} },
    note: (color) => ({
      className: "rounded-lg border p-3",
      style: {
        backgroundColor: "var(--card)",
        borderColor: "var(--border)",
        color: "var(--fg)",
      },
      accent: { kind: "dot", color: NOTE_ACCENT[color] },
      showPin: false,
      ruled: false,
    }),
  },

  ruled: {
    id: "ruled",
    label: "Ruled",
    blurb: "Warm index cards with a red margin, a color tab, and an underlined title.",
    allowHandFont: false,
    frame: NO_FRAME,
    surface: { className: "", style: {} },
    note: (color) => ({
      // pl-6 clears the red margin line (drawn by the card); the h3 rule gives
      // the classic index-card header underline.
      className:
        "rounded-lg border pt-4 pb-3.5 pr-3.5 pl-6 shadow-sm [&_h3]:border-b [&_h3]:border-black/10 [&_h3]:pb-1",
      style: {
        backgroundColor: "#fdfcf6",
        borderColor: "#e7e2d2",
        color: "#33312b",
        boxShadow: "0 1px 2px rgba(0,0,0,0.05), 0 6px 16px -10px rgba(0,0,0,0.2)",
      },
      accent: { kind: "strip", color: NOTE_ACCENT[color] },
      showPin: false,
      ruled: true,
    }),
  },
};

export function getNotesTheme(id: NotesThemeId): NotesTheme {
  return NOTES_THEMES[id] ?? NOTES_THEMES.clean;
}

// ---- per-board theme persistence (client-side) ------------------------------

const THEME_KEY_PREFIX = "pdash:notes-theme:";
export const DEFAULT_NOTES_THEME: NotesThemeId = "clean";

export function loadNotesTheme(pageId: string): NotesThemeId {
  if (typeof window === "undefined") return DEFAULT_NOTES_THEME;
  try {
    const v = window.localStorage.getItem(THEME_KEY_PREFIX + pageId);
    return isNotesThemeId(v) ? v : DEFAULT_NOTES_THEME;
  } catch {
    return DEFAULT_NOTES_THEME;
  }
}

export function saveNotesTheme(pageId: string, id: NotesThemeId): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(THEME_KEY_PREFIX + pageId, id);
  } catch {
    /* storage may be unavailable (private mode / quota) — non-fatal */
  }
}
