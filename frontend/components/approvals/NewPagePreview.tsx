"use client";

import { FilePlus2, LayoutDashboard, Lock, Plus, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import type { DashboardPreview } from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  home: "Home",
  agent: "Agent",
  custom: "Custom",
  system: "System",
  corkboard: "Corkboard",
  canvas: "Canvas",
};

/**
 * Visual preview for a `create_page` approval. The new page doesn't exist yet
 * and carries no modules, so instead of an empty module grid we render a
 * browser-window mock that shows the admin exactly what's being proposed: the
 * page name, its URL path, type, description, and an empty dashboard canvas
 * standing in for the modules that can be added once the page exists.
 */
export function NewPagePreview({ preview }: { preview: DashboardPreview }) {
  const { name, slug, description, type } = preview.page;
  const path = slug ? `/pages/${slug}` : "/pages/…";
  const typeLabel = type ? (TYPE_LABELS[type] ?? type) : null;

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-[var(--shadow-sm)]">
      {/* Browser chrome */}
      <div className="flex items-center gap-3 border-b border-[var(--border)] bg-[var(--muted)]/40 px-3 py-2">
        <div className="flex shrink-0 gap-1.5" aria-hidden="true">
          <span className="size-2.5 rounded-full bg-[var(--danger)]/60" />
          <span className="size-2.5 rounded-full bg-[var(--warning)]/70" />
          <span className="size-2.5 rounded-full bg-[var(--success)]/60" />
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1 font-mono text-xs text-[var(--muted-fg)]">
          <Lock className="size-3 shrink-0" />
          <span className="truncate">{path}</span>
        </div>
        <Badge tone="solid" className="shrink-0 shadow-[var(--shadow-sm)]">
          <Sparkles className="size-3" /> New page
        </Badge>
      </div>

      {/* Page hero */}
      <div className="border-b border-[var(--border)] px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
            <FilePlus2 className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-lg font-semibold tracking-tight text-[var(--fg)]">{name}</h3>
              {typeLabel && <Badge tone="neutral">{typeLabel}</Badge>}
            </div>
            {description ? (
              <p className="mt-1 text-sm text-[var(--muted-fg)]">{description}</p>
            ) : (
              <p className="mt-1 text-sm italic text-[var(--muted-fg)]/70">No description</p>
            )}
          </div>
        </div>
      </div>

      {/* Empty dashboard canvas */}
      <div className="px-5 py-5">
        <div className="mb-3 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
          <LayoutDashboard className="size-3.5" />
          <span>Dashboard</span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              aria-hidden="true"
              className="flex min-h-[5.5rem] flex-col gap-2 rounded-lg border-2 border-dashed border-[var(--border)] bg-[var(--muted)]/20 p-3"
            >
              <div className="h-2.5 w-1/2 rounded-full bg-[var(--muted)]" />
              <div className="h-2 w-3/4 rounded-full bg-[var(--muted)]/70" />
              <div className="h-2 w-2/3 rounded-full bg-[var(--muted)]/70" />
            </div>
          ))}
        </div>
        <div className="mt-4 flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-[var(--border)] bg-[var(--muted)]/10 px-3 py-2.5 text-xs text-[var(--muted-fg)]">
          <Plus className="size-3.5" />
          This page starts empty — modules can be added once it&apos;s created.
        </div>
      </div>
    </div>
  );
}
