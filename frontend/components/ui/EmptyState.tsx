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
 * Layout: large icon → headline → one-line hint → optional CTA.
 * Keep ``hint`` short; the CTA should be a single primary action.
 */
export function EmptyState({ icon, title, hint, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 rounded-lg border border-dashed border-[var(--border)] bg-[var(--card)] p-10 text-center",
        className,
      )}
    >
      {icon && (
        <div className="text-[var(--muted-fg)] mb-1" aria-hidden="true">
          {icon}
        </div>
      )}
      <p className="font-medium text-[var(--fg)]">{title}</p>
      {hint && <p className="text-sm text-[var(--muted-fg)] max-w-sm">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
