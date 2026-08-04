"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type EmptyStateProps = {
  icon?: ReactNode;
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
  className?: string;
};

/**
 * Friendly empty state used across pages.
 *
 * Layout: icon in a soft disc → headline → one-line hint → optional CTA.
 * Keep ``hint`` short; the CTA should be a single primary action.
 */
export function EmptyState({ icon, title, hint, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--card)]/60 px-6 py-12 text-center",
        className,
      )}
    >
      {icon && (
        <div
          className="mb-2 flex size-12 items-center justify-center rounded-full bg-[var(--muted)] text-[var(--muted-fg)]"
          aria-hidden="true"
        >
          {icon}
        </div>
      )}
      <p className="font-medium tracking-tight text-[var(--fg)]">{title}</p>
      {hint && <p className="text-sm text-[var(--muted-fg)] max-w-sm">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
