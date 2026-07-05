"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";

import { api } from "@/lib/api";

/**
 * Returns a `logout()` that clears the session and redirects to /login. Any API
 * error is intentionally swallowed — we redirect regardless.
 */
export function useLogout(): () => Promise<void> {
  const router = useRouter();
  return useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* ignore — redirect to login regardless */
    }
    router.replace("/login");
    router.refresh();
  }, [router]);
}
