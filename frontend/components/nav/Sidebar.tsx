"use client";

import {
  Activity,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Cog,
  Home,
  LogOut,
  Sparkles,
  X,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { type Page } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApprovalCount } from "@/lib/hooks/useApprovalCount";
import { useGuideDismissed } from "@/lib/hooks/useGuideDismissed";
import { useLogout } from "@/lib/hooks/useLogout";

import { ThemeToggle } from "../layout/ThemeToggle";
import { PageActionsMenu } from "./PageActionsMenu";
import { WarmLink } from "./WarmLink";

type SidebarProps = { pages: Page[] };

const SECTIONS = [
  {
    href: "/how-it-works",
    label: "How it Works",
    icon: Sparkles,
    match: (p: string) => p.startsWith("/how-it-works"),
    featured: true,
  },
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
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const { count: approvalCount } = useApprovalCount();
  const { dismissed: guideDismissed, dismiss: dismissGuide } = useGuideDismissed();
  const activePath = pendingPath ?? pathname;

  useEffect(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored === "1") setCollapsed(true);
  }, []);

  useEffect(() => {
    setPendingPath(null);
  }, [pathname]);

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
          <WarmLink
            href="/"
            onNavigate={() => setPendingPath("/")}
            className="font-semibold text-sm tracking-tight"
          >
            Home&nbsp;Base
          </WarmLink>
        )}
        <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle sidebar">
          {collapsed ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}
        </Button>
      </div>

      <nav className="flex flex-col gap-0.5 p-2">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const active = s.match(activePath);
          const featured = "featured" in s && s.featured;

          // The guide tab is dismissable; once hidden it lives in Settings → Help.
          if (featured) {
            if (guideDismissed) return null;
            return (
              <div
                key={s.href}
                className={cn(
                  "flex items-center rounded-md bg-[var(--accent)] text-[var(--accent-fg)]",
                  collapsed && "justify-center",
                )}
              >
                <WarmLink
                  href={s.href}
                  onNavigate={() => setPendingPath(s.href)}
                  className={cn(
                    "flex min-w-0 flex-1 items-center gap-3 px-2 py-2 text-sm font-medium hover:opacity-90",
                    collapsed && "justify-center",
                  )}
                  title={collapsed ? s.label : undefined}
                >
                  <Icon className="size-4 shrink-0" />
                  {!collapsed && <span className="flex-1">{s.label}</span>}
                </WarmLink>
                {!collapsed && (
                  <button
                    type="button"
                    onClick={dismissGuide}
                    aria-label="Hide How it Works from the sidebar"
                    title="Hide — find it later in Settings → Help"
                    className="mr-1 inline-flex size-7 shrink-0 items-center justify-center rounded-md text-[var(--accent-fg)] hover:bg-black/15"
                  >
                    <X className="size-3.5" />
                  </button>
                )}
              </div>
            );
          }

          return (
            <WarmLink
              key={s.href}
              href={s.href}
              onNavigate={() => setPendingPath(s.href)}
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
            </WarmLink>
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
            const active =
              p.slug === "home" ? activePath === "/" : activePath === `/pages/${p.slug}`;
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
                <WarmLink
                  href={href}
                  onNavigate={() => setPendingPath(href)}
                  className={cn(
                    "flex min-w-0 flex-1 items-center gap-3 px-2 py-1.5",
                    collapsed && "justify-center",
                  )}
                  title={collapsed ? p.name : undefined}
                >
                  <span className="inline-block size-1.5 shrink-0 rounded-full bg-[var(--muted-fg)]" />
                  {!collapsed && <span className="truncate">{p.name}</span>}
                </WarmLink>
                {!collapsed && (
                  <PageActionsMenu page={p} buttonClassName="mr-1" />
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
