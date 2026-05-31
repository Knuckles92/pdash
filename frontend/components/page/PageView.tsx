"use client";

import { LayoutDashboard, Pencil, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useChannel } from "@/components/layout/RealtimeProvider";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { api, type IframeAllowlistEntry, type Module, type Page } from "@/lib/api";

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
  const [liveModules, setLiveModules] = useState<Module[]>(modules);
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
    router.push(qs ? `${basePath}?${qs}` : basePath);
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{page.name}</h1>
          {page.description && (
            <p className="text-sm text-[var(--muted-fg)]">{page.description}</p>
          )}
        </div>
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
      </header>

      {sorted.length === 0 && !editMode ? (
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
      )}
    </div>
  );
}
