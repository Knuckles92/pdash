/** Returns the input href if its scheme is allowlisted, else null. */
const ALLOWED_SCHEMES = new Set(["http:", "https:", "mailto:"]);

export function safeHref(href: string | null | undefined): string | null {
  if (!href) return null;
  try {
    const u = new URL(href, "http://x");
    // If parsing required the base, it was a relative path — disallow.
    if (!href.includes(":") && u.protocol === "http:") return null;
    if (ALLOWED_SCHEMES.has(u.protocol)) return href;
    return null;
  } catch {
    return null;
  }
}
