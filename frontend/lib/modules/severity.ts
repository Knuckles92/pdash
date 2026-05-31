import type { Severity } from "./types";

/** Tailwind class map for severity chips/text. */
export function severityChipClass(s?: Severity | null): string {
  switch (s) {
    case "success":
      return "bg-green-500/15 text-green-700 dark:text-green-300 border-green-500/30";
    case "warning":
      return "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30";
    case "error":
      return "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30";
    case "info":
      return "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30";
    case "muted":
      return "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300 border-zinc-500/30";
    default:
      return "bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-500/20";
  }
}

export function severityDotClass(s?: Severity | null): string {
  switch (s) {
    case "success":
      return "bg-green-500";
    case "warning":
      return "bg-amber-500";
    case "error":
      return "bg-red-500";
    case "info":
      return "bg-sky-500";
    case "muted":
      return "bg-zinc-500";
    default:
      return "bg-zinc-400";
  }
}
