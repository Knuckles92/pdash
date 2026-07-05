"use client";

/**
 * "How it Works" guide visibility, persisted in localStorage.
 *
 * The guide tab is pinned to the sidebar (and mobile bottom nav) until the
 * admin dismisses it — it's meant to be seen once or twice. Once dismissed it
 * stays reachable from Settings → Help, where it can also be restored.
 *
 * Backed by a zustand store so the sidebar, bottom nav, and the guide page all
 * react to a dismiss/restore in the same tab. Default state is "not dismissed"
 * so the server-rendered HTML and first client render agree (no hydration
 * mismatch); the real value hydrates from localStorage on mount.
 */
import { useEffect } from "react";
import { create } from "zustand";

const LS_KEY = "pdash-guide-dismissed";

type GuideState = { dismissed: boolean; hydrated: boolean };

const useStore = create<GuideState>(() => ({ dismissed: false, hydrated: false }));

function hydrate(): void {
  if (useStore.getState().hydrated) return;
  let dismissed = false;
  try {
    dismissed = localStorage.getItem(LS_KEY) === "1";
  } catch {
    // localStorage unavailable — keep the default.
  }
  useStore.setState({ dismissed, hydrated: true });
}

export function dismissGuide(): void {
  try {
    localStorage.setItem(LS_KEY, "1");
  } catch {
    // ignore persistence failure; in-memory state still updates.
  }
  useStore.setState({ dismissed: true, hydrated: true });
}

export function restoreGuide(): void {
  try {
    localStorage.setItem(LS_KEY, "0");
  } catch {
    // ignore persistence failure; in-memory state still updates.
  }
  useStore.setState({ dismissed: false, hydrated: true });
}

export function useGuideDismissed(): {
  dismissed: boolean;
  dismiss: () => void;
  restore: () => void;
} {
  const dismissed = useStore((s) => s.dismissed);
  useEffect(() => {
    hydrate();
  }, []);
  return { dismissed, dismiss: dismissGuide, restore: restoreGuide };
}
