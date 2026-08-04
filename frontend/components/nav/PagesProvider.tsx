"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { useChannel } from "@/components/layout/RealtimeProvider";
import type { Page } from "@/lib/api";

type PagesContextValue = {
  pages: Page[];
  /** Drop a page from the nav immediately (e.g. right after a successful delete). */
  removePage: (id: string) => void;
};

const PagesContext = createContext<PagesContextValue>({
  pages: [],
  removePage: () => {},
});

/**
 * Client-side source of truth for the nav page list (Sidebar + MobilePagesDrawer).
 *
 * Seeded from the (app) layout's server fetch, then kept in sync two ways:
 *
 * - Realtime ``pages`` events apply directly to local state, so removals and
 *   renames show up instantly — the nav no longer depends on the
 *   ``router.refresh()`` RSC round-trip landing to update.
 * - ``router.refresh()`` still runs as reconciliation (and is the only path
 *   for ``page_added``, whose event payload isn't a complete ``Page``).
 *
 * ``removePage`` lets the delete flow (PageActionsMenu) clear the entry the
 * moment the DELETE succeeds, so a slow or dropped refresh can't leave a
 * deleted page lingering in the nav.
 */
export function PagesProvider({
  initialPages,
  children,
}: {
  initialPages: Page[];
  children: ReactNode;
}) {
  const router = useRouter();
  const [pages, setPages] = useState(initialPages);

  // Re-seed whenever the layout re-renders with fresh server data
  // (router.refresh() or a full navigation).
  useEffect(() => {
    setPages(initialPages);
  }, [initialPages]);

  useChannel("pages", (ev) => {
    if (ev.kind === "page_removed") {
      const id = ev.payload.page_id;
      if (typeof id === "string") {
        setPages((curr) => curr.filter((p) => p.id !== id));
      }
    } else if (ev.kind === "page_updated") {
      const patch = ev.payload.page as Partial<Page> | undefined;
      if (patch?.id) {
        if (patch.deleted_at) {
          setPages((curr) => curr.filter((p) => p.id !== patch.id));
        } else {
          setPages((curr) => curr.map((p) => (p.id === patch.id ? { ...p, ...patch } : p)));
        }
      }
    }
    if (
      ev.kind === "page_added" ||
      ev.kind === "page_updated" ||
      ev.kind === "page_removed" ||
      ev.kind === "resync_required"
    ) {
      router.refresh();
    }
  });

  const value = useMemo(
    () => ({
      pages,
      removePage: (id: string) => setPages((curr) => curr.filter((p) => p.id !== id)),
    }),
    [pages],
  );

  return <PagesContext.Provider value={value}>{children}</PagesContext.Provider>;
}

export function usePages(): PagesContextValue {
  return useContext(PagesContext);
}
