/**
 * Client-side defense-in-depth check that mirrors the server's allowlist
 * matching. The authoritative check is server-side (the iframe Pydantic
 * validator rejects unlisted hosts) but rendering a forbidden src is a bad
 * failure mode — so we re-check here.
 */

import type { IframeAllowlistEntry } from "@/lib/api";

function hostMatches(pattern: string, host: string): boolean {
  if (pattern.startsWith("*.")) {
    const suffix = pattern.slice(1); // ".example.com"
    if (host === suffix.slice(1)) return true;
    return host.endsWith(suffix);
  }
  return pattern.toLowerCase() === host.toLowerCase();
}

export function isAllowedIframeSrc(
  src: string,
  allowlist: IframeAllowlistEntry[],
): boolean {
  let url: URL;
  try {
    url = new URL(src);
  } catch {
    return false;
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return false;
  const host = url.hostname.toLowerCase();
  const path = url.pathname || "/";
  return allowlist.some((entry) => {
    if (!hostMatches(entry.host_pattern, host)) return false;
    if (entry.path_prefix && !path.startsWith(entry.path_prefix)) return false;
    return true;
  });
}
