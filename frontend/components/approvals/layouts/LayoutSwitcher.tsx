"use client";

import { cn } from "@/lib/cn";

import { APPROVAL_LAYOUTS } from "./index";

/**
 * Compact segmented control for hot-swapping the Approvals layout. Lives in the
 * Approvals page header; shows icon + label on wider screens, icon-only when
 * tight. Scrolls horizontally on very narrow viewports.
 */
export function LayoutSwitcher({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Approvals layout"
      className="flex shrink-0 gap-0.5 overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--card)] p-0.5 shadow-[var(--shadow-xs)]"
    >
      {APPROVAL_LAYOUTS.map((layout) => {
        const Icon = layout.icon;
        const active = layout.id === value;
        return (
          <button
            key={layout.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(layout.id)}
            title={layout.name}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
              active
                ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                : "text-[var(--muted-fg)] hover:bg-[var(--muted)] hover:text-[var(--fg)]",
            )}
          >
            <Icon className="size-4 shrink-0" />
            <span className="hidden sm:inline">{layout.name}</span>
          </button>
        );
      })}
    </div>
  );
}
