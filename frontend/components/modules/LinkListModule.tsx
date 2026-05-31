"use client";

import { ExternalLink } from "lucide-react";

import { cn } from "@/lib/cn";
import { safeHref } from "@/lib/modules/safehref";
import { severityChipClass } from "@/lib/modules/severity";
import type { LinkListConfig, LinkListData } from "@/lib/modules/types";

export function LinkListModule({
  data,
  config,
}: {
  data: LinkListData;
  config: LinkListConfig;
}) {
  const layout = config.layout ?? "list";
  const showDesc = config.show_descriptions ?? true;
  const links = (data.links ?? []).filter((l) => safeHref(l.href));

  if (links.length === 0) {
    return <p className="text-sm text-[var(--muted-fg)] italic">No links.</p>;
  }

  if (layout === "chips") {
    return (
      <div className="flex flex-wrap gap-2">
        {links.map((l, i) => (
          <a
            key={`${l.href}-${i}`}
            href={l.href}
            target={config.open_in_new_tab !== false ? "_blank" : undefined}
            rel="noopener noreferrer"
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs hover:bg-[var(--muted)]",
              severityChipClass(l.severity),
            )}
          >
            {l.label}
            {l.external && <ExternalLink className="size-3" />}
          </a>
        ))}
      </div>
    );
  }

  if (layout === "grid") {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {links.map((l, i) => (
          <a
            key={`${l.href}-${i}`}
            href={l.href}
            target={config.open_in_new_tab !== false ? "_blank" : undefined}
            rel="noopener noreferrer"
            className={cn(
              "flex flex-col gap-1 rounded-md border border-[var(--border)] p-3 hover:bg-[var(--muted)]",
            )}
          >
            <span className="flex items-center gap-1.5 text-sm font-medium">
              {l.label}
              {l.external && (
                <ExternalLink className="size-3 text-[var(--muted-fg)]" />
              )}
            </span>
            {showDesc && l.description ? (
              <span className="text-xs text-[var(--muted-fg)]">{l.description}</span>
            ) : null}
          </a>
        ))}
      </div>
    );
  }

  // list
  return (
    <ul className="flex flex-col">
      {links.map((l, i) => (
        <li key={`${l.href}-${i}`} className="border-b border-[var(--border)] last:border-b-0">
          <a
            href={l.href}
            target={config.open_in_new_tab !== false ? "_blank" : undefined}
            rel="noopener noreferrer"
            className="flex items-start justify-between gap-3 py-2 hover:bg-[var(--muted)] -mx-2 px-2 rounded-md"
          >
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">{l.label}</span>
              {showDesc && l.description ? (
                <span className="text-xs text-[var(--muted-fg)]">{l.description}</span>
              ) : null}
            </div>
            <ExternalLink className="size-3 mt-1 text-[var(--muted-fg)] shrink-0" />
          </a>
        </li>
      ))}
    </ul>
  );
}
