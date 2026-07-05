import { Fragment } from "react";

import { cn } from "@/lib/cn";

/**
 * The console-path eyebrow: a quiet mono breadcrumb (`pdash / approvals`)
 * rendered above page titles. Segments come from real structure (section,
 * page slug), never decoration. Decorative to screen readers — the h1 below
 * it carries the semantics.
 */
export function ConsolePath({
  segments,
  className,
}: {
  segments: string[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 font-mono text-[11px] tracking-wide text-[var(--muted-fg)]/80",
        className,
      )}
      aria-hidden="true"
    >
      <span>pdash</span>
      {segments.map((segment, i) => (
        <Fragment key={i}>
          <span className="text-[var(--accent)]/60">/</span>
          <span>{segment}</span>
        </Fragment>
      ))}
    </div>
  );
}
