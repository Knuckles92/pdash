"use client";

import { LayoutGrid } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Sheet } from "@/components/ui/Sheet";
import { cn } from "@/lib/cn";

import { PageActionsMenu } from "./PageActionsMenu";
import { usePages } from "./PagesProvider";
import { WarmLink } from "./WarmLink";

export function MobilePagesDrawer() {
  const { pages } = usePages();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const pathname = usePathname() ?? "/";
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const activePath = pendingPath ?? pathname;

  useEffect(() => {
    setPendingPath(null);
  }, [pathname]);

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return pages;
    return pages.filter(
      (p) => p.name.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q),
    );
  }, [pages, query]);

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden size-11"
        onClick={() => setOpen(true)}
        aria-label="Open pages"
      >
        <LayoutGrid className="size-5" />
      </Button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        side="left"
        title="Pages"
        description="Jump to a dashboard"
        className="max-w-[min(20rem,92vw)]"
      >
        {pages.length > 6 && (
          <div className="mb-3">
            <Input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter pages"
              aria-label="Filter pages"
              className="h-11"
            />
          </div>
        )}
        <nav className="flex flex-col gap-0.5">
          {filtered.map((p) => {
            const href = p.slug === "home" ? "/" : `/pages/${p.slug}`;
            const active =
              p.slug === "home" ? activePath === "/" : activePath === `/pages/${p.slug}`;
            return (
              <div
                key={p.id}
                className={cn(
                  "flex min-h-11 items-center rounded-lg transition-colors",
                  active
                    ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                    : "hover:bg-[var(--muted)]",
                )}
              >
                <WarmLink
                  href={href}
                  onClick={() => setOpen(false)}
                  onNavigate={() => setPendingPath(href)}
                  className="min-w-0 flex-1 truncate px-3 py-3 text-[15px]"
                >
                  {p.name}
                </WarmLink>
                <PageActionsMenu
                  page={p}
                  buttonClassName="mr-1"
                  buttonSizeClassName="size-10"
                  onAction={() => setOpen(false)}
                />
              </div>
            );
          })}
          {filtered.length === 0 && (
            <p className="px-3 py-6 text-sm text-[var(--muted-fg)]">No pages match.</p>
          )}
        </nav>
      </Sheet>
    </>
  );
}
