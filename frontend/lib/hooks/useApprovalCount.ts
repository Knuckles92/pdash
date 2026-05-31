"use client";

/**
 * Pending-approvals badge state, backed by SSE + REST refresh.
 *
 * - Count is refreshed on route change, tab focus, and initial mount.
 * - ``approval_pending`` events increment the count.
 * - ``approval_decided`` events decrement.
 * - ``resync_required`` triggers a re-fetch.
 */
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { create } from "zustand";

import { useRealtime } from "@/components/layout/RealtimeProvider";
import { api } from "@/lib/api";

type ApprovalCountState = {
  count: number;
  loading: boolean;
  inflight: Promise<void> | null;
};

const useApprovalCountStore = create<ApprovalCountState>(() => ({
  count: 0,
  loading: true,
  inflight: null,
}));

async function refreshFromServer(): Promise<void> {
  const state = useApprovalCountStore.getState();
  if (state.inflight) return state.inflight;
  const refresh = (async () => {
    try {
      const res = await api.listApprovalRequests({ limit: 1 });
      const next = res.total_pending ?? res.items.length;
      useApprovalCountStore.setState({ count: next, loading: false });
    } catch {
      useApprovalCountStore.setState({ loading: false });
    } finally {
      useApprovalCountStore.setState({ inflight: null });
    }
  })();
  useApprovalCountStore.setState({ inflight: refresh });
  return refresh;
}

/** Force a refresh (e.g. after an approve/deny mutation). */
export function refreshApprovalCount(): void {
  void refreshFromServer();
}

/** Locally bump (used for optimistic updates). */
export function adjustApprovalCount(delta: number): void {
  const current = useApprovalCountStore.getState().count;
  useApprovalCountStore.setState({ count: Math.max(0, current + delta) });
}

export function useApprovalCount(): { count: number; loading: boolean } {
  const count = useApprovalCountStore((s) => s.count);
  const loading = useApprovalCountStore((s) => s.loading);
  const pathname = usePathname();
  const { subscribe } = useRealtime();

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

  useEffect(() => {
    // First mount triggers a single hydration; subsequent mounts skip if we
    // already have a non-loading count.
    if (useApprovalCountStore.getState().loading) {
      void refreshFromServer();
    }
    const unsub = subscribe("approvals", (ev) => {
      if (ev.kind === "approval_pending") {
        const current = useApprovalCountStore.getState().count;
        useApprovalCountStore.setState({ count: current + 1 });
      } else if (ev.kind === "approval_decided") {
        const current = useApprovalCountStore.getState().count;
        useApprovalCountStore.setState({ count: Math.max(0, current - 1) });
      } else if (ev.kind === "resync_required") {
        void refreshFromServer();
      }
    });
    return () => {
      unsub();
    };
  }, [subscribe]);

  return { count, loading };
}
