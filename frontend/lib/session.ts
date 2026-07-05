/**
 * Server-side helpers for forwarding the admin's cookies to the backend.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { ApiError, api } from "./api";
import { CSRF_COOKIE, SESSION_COOKIE } from "./cookies";

/** Build a Cookie header from the incoming request's cookies. */
export const cookieHeaderFromRequest = cache(async (): Promise<string> => {
  const jar = await cookies();
  return jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
});

export const hasSessionCookie = cache(async (): Promise<boolean> => {
  const jar = await cookies();
  return jar.has(SESSION_COOKIE);
});

function isAuthError(err: unknown): boolean {
  return (
    err instanceof ApiError &&
    (err.status === 401 || err.code === "auth.invalid_session" || err.code === "auth.required")
  );
}

/**
 * Ensure the caller has a valid backend session. Redirects to /login when the
 * cookie is missing or rejected (stale signing secret, expired token, etc.).
 */
export const requireSession = cache(async (): Promise<string> => {
  const jar = await cookies();
  if (!jar.has(SESSION_COOKIE)) {
    redirect("/login");
  }
  const cookieHeader = await cookieHeaderFromRequest();
  try {
    await api.me({ cookieHeader });
  } catch (err) {
    if (isAuthError(err)) {
      redirect("/login");
    }
    throw err;
  }
  return cookieHeader;
});
