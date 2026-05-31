import { api, type IframeAllowlistEntry } from "@/lib/api";

/**
 * Load the iframe allowlist for server-rendered page views, returning an empty
 * list if the request fails. Iframe rendering degrades gracefully without it,
 * so a fetch error should not block the whole page.
 */
export async function loadIframeAllowlistSafe(
  cookieHeader?: string,
): Promise<IframeAllowlistEntry[]> {
  try {
    return await api.listIframeAllowlist({ cookieHeader });
  } catch {
    return [];
  }
}
