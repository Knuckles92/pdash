"use client";

import {
  Activity,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Cog,
  Home,
  LayoutDashboard,
  LogOut,
  Sparkles,
  X,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { useApprovalCount } from "@/lib/hooks/useApprovalCount";
import { useGuideDismissed } from "@/lib/hooks/useGuideDismissed";
import { useLogout } from "@/lib/hooks/useLogout";

import { ThemeToggle } from "../layout/ThemeToggle";
import { PageActionsMenu } from "./PageActionsMenu";
import { usePages } from "./PagesProvider";
import { WarmLink } from "./WarmLink";

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

export function Sidebar() {
  const { pages } = usePages();
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
        "hidden md:flex flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] transition-[width] duration-200",
        collapsed ? "w-16" : "w-60",
      )}
      aria-label="Primary navigation"
    >
      <div
        className={cn(
          "flex items-center px-3 py-3",
          collapsed ? "justify-center" : "justify-between",
        )}
      >
        {!collapsed && (
          <WarmLink
            href="/"
            onNavigate={() => setPendingPath("/")}
            className="flex items-center gap-2.5 px-1"
          >
            <span className="flex size-7 items-center justify-center rounded-lg bg-[var(--sidebar-accent)] text-[var(--sidebar-accent-fg)]">
              <LayoutDashboard className="size-4" />
            </span>
            <span className="font-mono text-sm font-medium text-[var(--sidebar-fg)]">pdash</span>
          </WarmLink>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggle}
          aria-label="Toggle sidebar"
          className="size-8 text-[var(--sidebar-muted-fg)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-fg)]"
        >
          {collapsed ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}
        </Button>
      </div>

      <nav className="flex flex-col gap-0.5 px-2 pt-1">
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
                  "mb-1 flex items-center rounded-lg bg-[var(--sidebar-accent)] text-[var(--sidebar-accent-fg)]",
                  collapsed && "justify-center",
                )}
              >
                <WarmLink
                  href={s.href}
                  onNavigate={() => setPendingPath(s.href)}
                  className={cn(
                    "flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-2 text-sm font-medium hover:opacity-90",
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
                    className="mr-1 inline-flex size-7 shrink-0 items-center justify-center rounded-md text-[var(--sidebar-accent-fg)] hover:bg-black/15"
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
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                active
                  ? "bg-[var(--sidebar-active)] font-medium text-[var(--sidebar-accent)]"
                  : "text-[var(--sidebar-muted-fg)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-fg)]",
                collapsed && "justify-center",
              )}
              title={collapsed ? s.label : undefined}
            >
              <Icon className="size-4 shrink-0" />
              {!collapsed && <span className="flex-1">{s.label}</span>}
              {!collapsed && "badge" in s && s.badge === "approvals" && approvalCount > 0 && (
                <Badge className="border-transparent bg-[var(--sidebar-accent)] font-mono text-[var(--sidebar-accent-fg)]">
                  {approvalCount}
                </Badge>
              )}
            </WarmLink>
          );
        })}
      </nav>

      <div className="mt-5 min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {!collapsed && (
          <div className="mb-1.5 px-2.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--sidebar-muted-fg)]/80">
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
                  "group flex items-center rounded-lg text-sm transition-colors",
                  active
                    ? "bg-[var(--sidebar-active)] font-medium text-[var(--sidebar-accent)]"
                    : "text-[var(--sidebar-muted-fg)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-fg)]",
                  collapsed && "justify-center",
                )}
              >
                <WarmLink
                  href={href}
                  onNavigate={() => setPendingPath(href)}
                  className={cn(
                    "flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-1.5",
                    collapsed && "justify-center",
                  )}
                  title={collapsed ? p.name : undefined}
                >
                  <span
                    className={cn(
                      "inline-block size-1.5 shrink-0 rounded-full",
                      active ? "bg-[var(--sidebar-accent)]" : "bg-[var(--border-strong)]",
                    )}
                  />
                  {!collapsed && <span className="truncate">{p.name}</span>}
                </WarmLink>
                {!collapsed && (
                  <PageActionsMenu
                    page={p}
                    buttonClassName="mr-1 text-[var(--sidebar-muted-fg)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-fg)]"
                  />
                )}
              </div>
            );
          })}
        </nav>
      </div>

      <div className="flex items-center justify-between border-t border-[var(--sidebar-border)] p-2">
        <ThemeToggle className="text-[var(--sidebar-muted-fg)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-fg)]" />
        <Button
          variant="ghost"
          size="icon"
          onClick={logout}
          aria-label="Log out"
          title="Log out"
          className="text-[var(--sidebar-muted-fg)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-fg)]"
        >
          <LogOut className="size-4" />
        </Button>
      </div>
    </aside>
  );
}
