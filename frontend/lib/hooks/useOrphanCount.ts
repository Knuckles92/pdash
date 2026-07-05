"use client";

/**
 * Orphan-files badge state for the Settings → Files tab.
 *
 * Refreshed on route change, tab focus, and after a Files mutation (call
 * ``refreshOrphanCount``). Unlike approvals there's no SSE wiring — orphaned
 * drops are infrequent, so a focus/route refresh is plenty. The count is
 * "needs attention" = unclaimed inbox files + registered files whose bytes
 * went missing.
 */
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { create } from "zustand";

import { api } from "@/lib/api";

type OrphanCountState = {
  count: number;
  loading: boolean;
  inflight: Promise<void> | null;
};

const useOrphanCountStore = create<OrphanCountState>(() => ({
  count: 0,
  loading: true,
  inflight: null,
}));

async function refreshFromServer(): Promise<void> {
  const state = useOrphanCountStore.getState();
  if (state.inflight) return state.inflight;
  const refresh = (async () => {
    try {
      const res = await api.orphanCount();
      useOrphanCountStore.setState({ count: res.total, loading: false });
    } catch {
      useOrphanCountStore.setState({ loading: false });
    } finally {
      useOrphanCountStore.setState({ inflight: null });
    }
  })();
  useOrphanCountStore.setState({ inflight: refresh });
  return refresh;
}

/** Force a refresh (e.g. after registering/deleting a file). */
export function refreshOrphanCount(): void {
  void refreshFromServer();
}

export function useOrphanCount(): { count: number; loading: boolean } {
  const count = useOrphanCountStore((s) => s.count);
  const loading = useOrphanCountStore((s) => s.loading);
  const pathname = usePathname();

  useEffect(() => {
    void refreshFromServer();
  }, [pathname]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void refreshFromServer();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  return { count, loading };
}
