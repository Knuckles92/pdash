/**
 * Tiny client-side cookie reader. Server components use next/headers cookies() instead.
 */
export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const target = `${encodeURIComponent(name)}=`;
  for (const raw of document.cookie.split(";")) {
    const c = raw.trim();
    if (c.startsWith(target)) {
      return decodeURIComponent(c.slice(target.length));
    }
  }
  return null;
}

export const CSRF_COOKIE = "csrf_token";
export const SESSION_COOKIE = "session";
