"use client";

import { LayoutDashboard, Pencil, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ConsolePath } from "@/components/layout/ConsolePath";
import { useChannel } from "@/components/layout/RealtimeProvider";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { api, type IframeAllowlistEntry, type Module, type Page } from "@/lib/api";

import { CanvasView } from "./CanvasView";
import { CorkboardBoard } from "./CorkboardBoard";
import { EditablePageGrid } from "./EditablePageGrid";
import { PageGrid } from "./PageGrid";

type Props = {
  page: Page;
  modules: Module[];
  iframeAllowlist?: IframeAllowlistEntry[];
};

export function PageView({ page, modules, iframeAllowlist }: Props) {
  const search = useSearchParams();
  const router = useRouter();
  const editMode = search?.get("edit") === "1";

  // Phase 5: subscribe to page:<id> for live module add/update/remove/reorder.
  // Reset synchronously on page change — a useEffect reset would leave one
  // render with the previous page's modules, which can mount an html iframe
  // and then rewrite its srcdoc when the new page's modules arrive (blank frame).
  const [liveModules, setLiveModules] = useState<Module[]>(modules);
  const [livePageId, setLivePageId] = useState(page.id);
  if (page.id !== livePageId) {
    setLivePageId(page.id);
    setLiveModules(modules);
  }
  useEffect(() => {
    setLiveModules(modules);
  }, [modules]);

  useChannel(`page:${page.id}`, (ev) => {
    // Events carry only a slim module summary, so refetch the full list.
    const refetchModules = () =>
      void api.listModules({ page_id: page.id }).then(({ items }) => setLiveModules(items));
    if (ev.kind === "module_added") {
      refetchModules();
    } else if (ev.kind === "module_updated") {
      refetchModules();
    } else if (ev.kind === "module_removed") {
      const mid = ev.payload.module_id as string | undefined;
      if (!mid) return;
      setLiveModules((prev) => prev.filter((x) => x.id !== mid));
    } else if (ev.kind === "modules_reordered") {
      const order = ev.payload.order as string[] | undefined;
      if (!order) return;
      setLiveModules((prev) => {
        const byId = new Map(prev.map((m) => [m.id, m]));
        const reordered: Module[] = [];
        order.forEach((id, i) => {
          const m = byId.get(id);
          if (m) {
            reordered.push({ ...m, position: i });
            byId.delete(id);
          }
        });
        for (const remaining of byId.values()) reordered.push(remaining);
        return reordered;
      });
    } else if (ev.kind === "resync_required") {
      refetchModules();
    }
  });

  const sorted = useMemo(
    () =>
      [...liveModules]
        .filter((m) => !m.deleted_at)
        .sort((a, b) => a.position - b.position || a.created_at.localeCompare(b.created_at)),
    [liveModules],
  );

  function toggleEdit() {
    const params = new URLSearchParams(Array.from(search?.entries() ?? []));
    if (editMode) params.delete("edit");
    else params.set("edit", "1");
    const qs = params.toString();
    const basePath = page.slug === "home" ? "/" : `/pages/${page.slug}`;
    router.push(qs ? `${basePath}?${qs}` : basePath, { scroll: false });
  }

  const isCorkboard = page.kind === "corkboard";
  const isCanvas = page.kind === "canvas";

  const body = isCorkboard ? (
    <CorkboardBoard pageId={page.id} modules={sorted} />
  ) : isCanvas && !editMode ? (
    <CanvasView modules={sorted} onEnterEdit={toggleEdit} />
  ) : sorted.length === 0 && !editMode ? (
      <EmptyState
        icon={<LayoutDashboard className="size-12" />}
        title={page.slug === "home" ? "Your dashboard is empty" : "This page has no modules yet"}
        hint="Modules are the building blocks of every page. Drop in a status panel, a chart, or a quick-launch button."
        action={
          <Button onClick={toggleEdit}>
            <Pencil className="size-4" /> Enter edit mode
          </Button>
        }
      />
    ) : editMode ? (
      <EditablePageGrid pageId={page.id} initialModules={sorted} />
    ) : (
      <PageGrid modules={sorted} iframeAllowlist={iframeAllowlist} />
    );

  return (
    <div className="grid grid-cols-[1fr_auto] gap-x-3">
      <div className="flex min-w-0 flex-col gap-5">
        <header className="flex flex-col gap-1">
          <ConsolePath
            segments={page.slug === "home" ? ["home"] : ["pages", page.slug]}
          />
          <h1 className="font-display text-xl font-semibold tracking-tight">{page.name}</h1>
          {page.description && (
            <p className="text-sm text-[var(--muted-fg)]">{page.description}</p>
          )}
        </header>
        {body}
      </div>
      <div>
        {!isCorkboard && (
          <div className="sticky top-4 z-20 shrink-0">
            <Button variant={editMode ? "primary" : "secondary"} size="sm" onClick={toggleEdit}>
              {editMode ? (
                <>
                  <X className="size-4" /> Done
                </>
              ) : (
                <>
                  <Pencil className="size-4" /> Edit
                </>
              )}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
