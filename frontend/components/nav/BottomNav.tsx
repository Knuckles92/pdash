"use client";

import { Activity, CheckCircle2, Cog, Home, Sparkles } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import { useApprovalCount } from "@/lib/hooks/useApprovalCount";
import { useGuideDismissed } from "@/lib/hooks/useGuideDismissed";

import { WarmLink } from "./WarmLink";

const ITEMS = [
  {
    href: "/how-it-works",
    label: "Guide",
    icon: Sparkles,
    match: (p: string) => p.startsWith("/how-it-works"),
    featured: true,
  },
  { href: "/", label: "Home", icon: Home, match: (p: string) => p === "/" || p.startsWith("/pages") },
  {
    href: "/approvals",
    label: "Approvals",
    icon: CheckCircle2,
    match: (p: string) => p.startsWith("/approvals"),
  },
  {
    href: "/activity",
    label: "Activity",
    icon: Activity,
    match: (p: string) => p.startsWith("/activity"),
  },
  {
    href: "/settings/agents",
    label: "Settings",
    icon: Cog,
    match: (p: string) => p.startsWith("/settings"),
  },
] as const;

export function BottomNav() {
  const pathname = usePathname() ?? "/";
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const { count: approvalCount } = useApprovalCount();
  const { dismissed: guideDismissed } = useGuideDismissed();
  const items = ITEMS.filter((it) => !("featured" in it && it.featured && guideDismissed));
  const activePath = pendingPath ?? pathname;

  useEffect(() => {
    setPendingPath(null);
  }, [pathname]);

  return (
    <nav
      className="md:hidden fixed inset-x-0 bottom-0 z-40 border-t border-[var(--border)] bg-[var(--card)]/90 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      aria-label="Primary navigation"
    >
      <ul className={cn("grid", items.length === 5 ? "grid-cols-5" : "grid-cols-4")}>
        {items.map((it) => {
          const Icon = it.icon;
          const active = it.match(activePath);
          return (
            <li key={it.href}>
              <WarmLink
                href={it.href}
                onNavigate={() => setPendingPath(it.href)}
                className={cn(
                  "relative flex flex-col items-center justify-center gap-1 py-2 text-[11px] font-medium",
                  "featured" in it && it.featured
                    ? "text-[var(--accent)]"
                    : active
                      ? "text-[var(--accent)]"
                      : "text-[var(--muted-fg)]",
                )}
              >
                <Icon className="size-5" />
                <span>{it.label}</span>
                {it.label === "Approvals" && approvalCount > 0 && (
                  <Badge tone="solid" className="absolute top-1 right-1/3">
                    {approvalCount}
                  </Badge>
                )}
              </WarmLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
