"use client";

import { useRouter } from "next/navigation";

import { useChannel } from "@/components/layout/RealtimeProvider";

/**
 * Keeps the server-rendered page list (Sidebar + MobilePagesDrawer) in sync
 * with realtime page mutations.
 *
 * The page list is fetched in the (app) layout server component, so when a
 * page is added / renamed / removed — e.g. an agent's "create page" proposal
 * is approved — we ask Next to re-run that RSC. ``router.refresh()`` refetches
 * server data while preserving client state. Without this the new page only
 * appears after a manual browser refresh.
 *
 * ``pages`` is an always-on realtime channel (see RealtimeProvider), so this
 * just attaches a handler to the existing EventSource.
 */
export function PageListRefresher() {
  const router = useRouter();
  useChannel("pages", (ev) => {
    if (
      ev.kind === "page_added" ||
      ev.kind === "page_updated" ||
      ev.kind === "page_removed" ||
      ev.kind === "resync_required"
    ) {
      router.refresh();
    }
  });
  return null;
}
