"use client";

import {
  Activity,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Cog,
  Home,
  LogOut,
  MoreHorizontal,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { type Page } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApprovalCount } from "@/lib/hooks/useApprovalCount";
import { useLogout } from "@/lib/hooks/useLogout";

import { ThemeToggle } from "../layout/ThemeToggle";

type SidebarProps = { pages: Page[] };

const SECTIONS = [
  { href: "/", label: "Home", icon: Home, match: (p: string) => p === "/" },
  {
    href: "/approvals",
    label: "Approvals",
    icon: CheckCircle2,
    match: (p: string) => p.startsWith("/approvals"),
    badge: "approvals",
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

const LS_KEY = "pdash-sidebar-collapsed";

export function Sidebar({ pages }: SidebarProps) {
  const pathname = usePathname() ?? "/";
  const logout = useLogout();
  const [collapsed, setCollapsed] = useState(false);
  const { count: approvalCount } = useApprovalCount();

  useEffect(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored === "1") setCollapsed(true);
  }, []);

  const toggle = () => {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem(LS_KEY, next ? "1" : "0");
      return next;
    });
  };

  return (
    <aside
      className={cn(
        "hidden md:flex flex-col border-r border-[var(--border)] bg-[var(--card)] transition-[width] duration-200",
        collapsed ? "w-16" : "w-60",
      )}
      aria-label="Primary navigation"
    >
      <div className="flex items-center justify-between px-3 py-3 border-b border-[var(--border)]">
        {!collapsed && (
          <Link href="/" className="font-semibold text-sm tracking-tight">
            Home&nbsp;Base
          </Link>
        )}
        <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle sidebar">
          {collapsed ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}
        </Button>
      </div>

      <nav className="flex flex-col gap-0.5 p-2">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const active = s.match(pathname);
          return (
            <Link
              key={s.href}
              href={s.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-2 py-2 text-sm",
                active
                  ? "bg-[var(--muted)] text-[var(--fg)] font-medium"
                  : "text-[var(--muted-fg)] hover:text-[var(--fg)] hover:bg-[var(--muted)]",
                collapsed && "justify-center",
              )}
              title={collapsed ? s.label : undefined}
            >
              <Icon className="size-4 shrink-0" />
              {!collapsed && <span className="flex-1">{s.label}</span>}
              {!collapsed && "badge" in s && s.badge === "approvals" && approvalCount > 0 && (
                <Badge className="bg-[var(--accent)] text-[var(--accent-fg)] border-transparent">
                  {approvalCount}
                </Badge>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mt-4 px-2">
        {!collapsed && (
          <div className="px-2 mb-1 text-[10px] uppercase tracking-wider text-[var(--muted-fg)]">
            Pages
          </div>
        )}
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
                  "flex items-center rounded-md text-sm",
                  active
                    ? "bg-[var(--muted)] text-[var(--fg)] font-medium"
                    : "text-[var(--muted-fg)] hover:text-[var(--fg)] hover:bg-[var(--muted)]",
                  collapsed && "justify-center",
                )}
              >
                <Link
                  href={href}
                  className={cn(
                    "flex min-w-0 flex-1 items-center gap-3 px-2 py-1.5",
                    collapsed && "justify-center",
                  )}
                  title={collapsed ? p.name : undefined}
                >
                  <span className="inline-block size-1.5 shrink-0 rounded-full bg-[var(--muted-fg)]" />
                  {!collapsed && <span className="truncate">{p.name}</span>}
                </Link>
                {!collapsed && (
                  <Link
                    href={rulesHref}
                    className="mr-1 inline-flex size-7 shrink-0 items-center justify-center rounded-md text-[var(--muted-fg)] hover:bg-[var(--card)] hover:text-[var(--fg)]"
                    aria-label={`Manage rules for ${p.name}`}
                    title={`Manage rules for ${p.name}`}
                  >
                    <MoreHorizontal className="size-4" />
                  </Link>
                )}
              </div>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto flex items-center justify-between p-2 border-t border-[var(--border)]">
        <ThemeToggle />
        <Button variant="ghost" size="icon" onClick={logout} aria-label="Log out" title="Log out">
          <LogOut className="size-4" />
        </Button>
      </div>
    </aside>
  );
}
