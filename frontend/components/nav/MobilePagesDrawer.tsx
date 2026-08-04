"use client";

import { LayoutGrid } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { cn } from "@/lib/cn";

import { PageActionsMenu } from "./PageActionsMenu";
import { usePages } from "./PagesProvider";
import { WarmLink } from "./WarmLink";

export function MobilePagesDrawer() {
  const { pages } = usePages();
  const [open, setOpen] = useState(false);
  const pathname = usePathname() ?? "/";
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const activePath = pendingPath ?? pathname;

  useEffect(() => {
    setPendingPath(null);
  }, [pathname]);

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
            const active =
              p.slug === "home" ? activePath === "/" : activePath === `/pages/${p.slug}`;
            return (
              <div
                key={p.id}
                className={cn(
                  "flex items-center rounded-lg transition-colors",
                  active
                    ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                    : "hover:bg-[var(--muted)]",
                )}
              >
                <WarmLink
                  href={href}
                  onClick={() => setOpen(false)}
                  onNavigate={() => setPendingPath(href)}
                  className="min-w-0 flex-1 truncate px-3 py-2 text-sm"
                >
                  {p.name}
                </WarmLink>
                <PageActionsMenu
                  page={p}
                  buttonClassName="mr-1"
                  buttonSizeClassName="size-9"
                  onAction={() => setOpen(false)}
                />
              </div>
            );
          })}
        </nav>
      </Sheet>
    </>
  );
}
