import type { Severity } from "./types";

/** Chip/callout class map for severities, on the theme's status tokens. */
export function severityChipClass(s?: Severity | string | null): string {
  switch (s) {
    case "success":
      return "border-[var(--success)]/25 bg-[var(--success-soft)] text-[var(--success)]";
    case "warning":
      return "border-[var(--warning)]/25 bg-[var(--warning-soft)] text-[var(--warning)]";
    case "error":
      return "border-[var(--danger)]/25 bg-[var(--danger-soft)] text-[var(--danger)]";
    case "info":
      return "border-[var(--info)]/25 bg-[var(--info-soft)] text-[var(--info)]";
    case "muted":
      return "border-[var(--border)] bg-[var(--muted)] text-[var(--muted-fg)]";
    default:
      return "border-[var(--border)] bg-[var(--muted)]/60 text-[var(--muted-fg)]";
  }
}

export function severityDotClass(s?: Severity | string | null): string {
  switch (s) {
    case "success":
      return "bg-[var(--success)]";
    case "warning":
      return "bg-[var(--warning)]";
    case "error":
      return "bg-[var(--danger)]";
    case "info":
      return "bg-[var(--info)]";
    case "muted":
      return "bg-[var(--muted-fg)]";
    default:
      return "bg-[var(--border-strong)]";
  }
}
