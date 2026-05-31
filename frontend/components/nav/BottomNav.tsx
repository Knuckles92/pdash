"use client";

import { Activity, CheckCircle2, Cog, Home } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import { useApprovalCount } from "@/lib/hooks/useApprovalCount";

const ITEMS = [
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
  const { count: approvalCount } = useApprovalCount();
  return (
    <nav
      className="md:hidden fixed inset-x-0 bottom-0 z-40 border-t border-[var(--border)] bg-[var(--card)] pb-[env(safe-area-inset-bottom)]"
      aria-label="Primary navigation"
    >
      <ul className="grid grid-cols-4">
        {ITEMS.map((it) => {
          const Icon = it.icon;
          const active = it.match(pathname);
          return (
            <li key={it.href}>
              <Link
                href={it.href}
                className={cn(
                  "relative flex flex-col items-center justify-center gap-1 py-2 text-[11px]",
                  active ? "text-[var(--fg)]" : "text-[var(--muted-fg)]",
                )}
              >
                <Icon className="size-5" />
                <span>{it.label}</span>
                {it.label === "Approvals" && approvalCount > 0 && (
                  <Badge className="absolute top-1 right-1/3 bg-[var(--accent)] text-[var(--accent-fg)] border-transparent">
                    {approvalCount}
                  </Badge>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
