"use client";

import { LayoutGrid, MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import type { Page } from "@/lib/api";
import { cn } from "@/lib/cn";

export function MobilePagesDrawer({ pages }: { pages: Page[] }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname() ?? "/";

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={() => setOpen(true)}
        aria-label="Open pages"
      >
        <LayoutGrid className="size-5" />
      </Button>
      <Sheet open={open} onClose={() => setOpen(false)} side="left" title="Pages">
        <nav className="flex flex-col gap-0.5">
          {pages.map((p) => {
            const href = p.slug === "home" ? "/" : `/pages/${p.slug}`;
            const rulesHref = `/settings/rules?page_id=${encodeURIComponent(p.id)}`;
            const active =
              p.slug === "home" ? pathname === "/" : pathname === `/pages/${p.slug}`;
            return (
              <div
                key={p.id}
                className={cn(
                  "flex items-center rounded-md",
                  active
                    ? "bg-[var(--muted)] font-medium"
                    : "hover:bg-[var(--muted)]",
                )}
              >
                <Link
                  href={href}
                  onClick={() => setOpen(false)}
                  className="min-w-0 flex-1 truncate px-3 py-2 text-sm"
                >
                  {p.name}
                </Link>
                <Link
                  href={rulesHref}
                  onClick={() => setOpen(false)}
                  className="mr-1 inline-flex size-9 shrink-0 items-center justify-center rounded-md text-[var(--muted-fg)] hover:bg-[var(--card)] hover:text-[var(--fg)]"
                  aria-label={`Manage rules for ${p.name}`}
                  title={`Manage rules for ${p.name}`}
                >
                  <MoreHorizontal className="size-4" />
                </Link>
              </div>
            );
          })}
        </nav>
      </Sheet>
    </>
  );
}
