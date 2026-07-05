/** Format a byte count as a short human string (e.g. 1.4 MB). */
export function humanizeBytes(n?: number | null): string | null {
  if (n == null) return null;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${i === 0 || v >= 10 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}
