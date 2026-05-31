/**
 * Shared value formatters for module renderers, so every module type displays
 * bytes and durations identically. Import these instead of re-implementing.
 */

/** Format a byte count as a human-readable string, e.g. `1.5 KB`. */
export function humanizeBytes(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let value = Math.abs(n);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const sign = n < 0 ? "-" : "";
  return `${sign}${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`;
}

/** Format a millisecond duration as a human-readable string, e.g. `1.5 s`. */
export function humanizeDurationMs(ms: number): string {
  if (!Number.isFinite(ms)) return String(ms);
  const abs = Math.abs(ms);
  if (abs < 1) return `${ms.toFixed(2)} ms`;
  if (abs < 1000) return `${ms.toFixed(0)} ms`;
  const seconds = ms / 1000;
  if (Math.abs(seconds) < 60) return `${seconds.toFixed(1)} s`;
  const minutes = seconds / 60;
  if (Math.abs(minutes) < 60) return `${minutes.toFixed(1)} m`;
  const hours = minutes / 60;
  return `${hours.toFixed(2)} h`;
}
