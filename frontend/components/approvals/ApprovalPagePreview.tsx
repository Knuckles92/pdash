"use client";

import { LayoutDashboard } from "lucide-react";
import { useMemo } from "react";

import { ModuleHost } from "@/components/modules/ModuleHost";
import { ModuleRenderer } from "@/components/modules/ModuleRenderer";
import { Badge } from "@/components/ui/Badge";
import type { DashboardPreview, IframeAllowlistEntry, Module } from "@/lib/api";
import { cn } from "@/lib/cn";
import { colspanClass } from "@/lib/modules/grid";

type DisplayItem =
  | { kind: "module"; module: Module }
  | { kind: "removed"; module: Module };

function pinKey(m: Module): number {
  if (m.type === "notification") {
    const cfg = m.config as { pin_to_top?: boolean } | undefined;
    if (cfg?.pin_to_top) return 0;
  }
  return 1;
}

function buildDisplayItems(preview: DashboardPreview): DisplayItem[] {
  const items: DisplayItem[] = preview.modules.map((module) => ({
    kind: "module",
    module,
  }));
  for (const removed of preview.highlight.removed_modules ?? []) {
    items.push({ kind: "removed", module: removed as Module });
  }
  return items.sort((a, b) => {
    const pin = pinKey(a.module) - pinKey(b.module);
    if (pin !== 0) return pin;
    const pos = a.module.position - b.module.position;
    if (pos !== 0) return pos;
    return a.module.created_at.localeCompare(b.module.created_at);
  });
}

function RemovedModulePlaceholder({ module: m }: { module: Module }) {
  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border-2 border-dashed border-[var(--danger)]/50",
        "bg-[var(--danger)]/5 min-h-[6rem]",
      )}
    >
      <div className="flex items-center gap-2 border-b border-[var(--danger)]/20 px-3 py-2">
        <span className="truncate text-sm font-medium text-[var(--fg)]">
          {m.title ?? `Untitled ${m.type}`}
        </span>
        <Badge className="ml-auto shrink-0 bg-[var(--danger)]/15 text-[var(--danger)] border-[var(--danger)]/30">
          Will be removed
        </Badge>
      </div>
      <div className="flex flex-1 items-center justify-center p-4 text-xs text-[var(--muted-fg)]">
        This module will be deleted if approved.
      </div>
    </div>
  );
}

export function ApprovalPagePreview({
  preview,
  iframeAllowlist,
}: {
  preview: DashboardPreview;
  iframeAllowlist?: IframeAllowlistEntry[];
}) {
  const highlighted = useMemo(
    () => new Set(preview.highlight.module_ids),
    [preview.highlight.module_ids],
  );

  const items = useMemo(() => buildDisplayItems(preview), [preview]);

  const changeLabel =
    preview.highlight.change === "create"
      ? "New module"
      : preview.highlight.change === "update"
        ? "Updated module"
        : "Removed module";

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <LayoutDashboard className="size-3.5 text-[var(--muted-fg)]" />
        <span className="font-medium text-sm">{preview.page.name}</span>
        <span className="text-[var(--muted-fg)]">/{preview.page.slug}</span>
        <Badge className="bg-[var(--muted)] text-[var(--fg)] border-[var(--border)]">
          {changeLabel}
        </Badge>
      </div>

      {items.length === 0 ? (
        <p className="text-xs text-[var(--muted-fg)]">No modules on this page.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => {
            if (item.kind === "removed") {
              return (
                <RemovedModulePlaceholder key={`removed-${item.module.id}`} module={item.module} />
              );
            }
            const m = item.module;
            const isHighlighted = highlighted.has(m.id);
            return (
              <div key={m.id} className={cn("relative", colspanClass(m.grid))}>
                {isHighlighted && (
                  <Badge className="absolute -top-2 right-2 z-10 bg-[var(--accent)] text-[var(--accent-fg)] border-transparent shadow-sm">
                    Proposed
                  </Badge>
                )}
                <ModuleHost
                  module={m}
                  className={cn(
                    isHighlighted && "ring-2 ring-[var(--accent)]/60 shadow-sm",
                    !isHighlighted && preview.highlight.change !== "delete" && "opacity-80",
                  )}
                >
                  <ModuleRenderer module={m} iframeAllowlist={iframeAllowlist} preview />
                </ModuleHost>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
