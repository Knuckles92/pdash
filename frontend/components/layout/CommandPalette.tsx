"use client";

/**
 * Global command palette (⌘K / Ctrl+K).
 *
 * Built on top of `cmdk`. Exposes three groups:
 * 1. Pages — fuzzy nav to any non-deleted page (home + custom + agent).
 * 2. Commands — toggle edit mode, dark mode, logout, go to approvals/etc.
 * 3. Recent activity — last 20 rows; click jumps to /activity?focus=<id>.
 *
 * Mobile users tap the icon button in the top app bar; desktop users hit
 * ⌘K. Esc / outside-click closes. Selecting an item runs its `onSelect`
 * and closes the palette.
 *
 * Note: this component must NOT be SSR-rendered (cmdk requires the DOM),
 * so it lives behind a `useEffect`-driven mount gate.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Command } from "cmdk";
import {
  Activity,
  CheckCircle2,
  Cog,
  FileText,
  Home,
  LogOut,
  Moon,
  PencilLine,
  Search,
  ShieldCheck,
  Sun,
} from "lucide-react";

import { api, type ActivityLogRow, type Page } from "@/lib/api";
import { useLogout } from "@/lib/hooks/useLogout";

type Props = {
  open: boolean;
  onClose: () => void;
};

const SETTINGS_PAGES: Array<{ slug: string; name: string }> = [
  { slug: "agents", name: "Settings — Agents" },
  { slug: "pages", name: "Settings — Pages" },
  { slug: "rules", name: "Settings — Approval rules" },
  { slug: "iframe-allowlist", name: "Settings — Iframe allowlist" },
  { slug: "action-targets", name: "Settings — Action targets" },
];

export function CommandPalette({ open, onClose }: Props) {
  const router = useRouter();
  const [pages, setPages] = useState<Page[]>([]);
  const [recentActivity, setRecentActivity] = useState<ActivityLogRow[]>([]);
  const [query, setQuery] = useState("");

  // Lazy-load pages + recent activity on first open so we don't pay the
  // network cost up front.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void (async () => {
      try {
        const [p, a] = await Promise.all([
          api.listPages(),
          api.listActivity({ limit: 20 }),
        ]);
        if (cancelled) return;
        setPages(p.items.filter((x) => !x.deleted_at));
        setRecentActivity(a.items);
      } catch {
        // ignore — palette still works for static commands
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Close on Esc.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const navigateAndClose = useCallback(
    (href: string) => {
      onClose();
      router.push(href);
    },
    [onClose, router],
  );

  const toggleEdit = useCallback(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("edit") === "1") {
      url.searchParams.delete("edit");
    } else {
      url.searchParams.set("edit", "1");
    }
    router.push(url.pathname + url.search, { scroll: false });
    onClose();
  }, [router, onClose]);

  const toggleDark = useCallback(() => {
    if (typeof document === "undefined") return;
    const current = document.documentElement.dataset.theme;
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem("pdash-theme", next);
    } catch {
      /* ignore */
    }
    onClose();
  }, [onClose]);

  const doLogout = useLogout();
  const logout = useCallback(async () => {
    onClose();
    await doLogout();
  }, [onClose, doLogout]);

  const formattedActivity = useMemo(
    () =>
      recentActivity.map((row) => ({
        id: row.id,
        label: `${row.action_type} → ${row.outcome}`,
        sub:
          (row.target_kind ? `${row.target_kind}:${row.target_id ?? ""}` : "") ||
          row.actor_id ||
          "",
      })),
    [recentActivity],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-[var(--overlay)] p-4 pt-[10vh] backdrop-blur-sm anim-overlay-in"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-[var(--shadow-lg)] anim-pop-in"
        onClick={(e) => e.stopPropagation()}
      >
        <Command label="Command Palette" className="flex flex-col">
          <div className="flex items-center gap-2.5 border-b border-[var(--border)] px-4 py-3">
            <Search className="size-4 shrink-0 text-[var(--muted-fg)]" />
            <Command.Input
              value={query}
              onValueChange={setQuery}
              autoFocus
              placeholder="Search pages, commands, recent activity…"
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--muted-fg)]/70"
            />
            <kbd className="hidden rounded-md border border-[var(--border)] bg-[var(--muted)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--muted-fg)] md:inline">
              esc
            </kbd>
          </div>
          <Command.List className="max-h-[60vh] overflow-y-auto p-2 text-sm [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-[var(--muted-fg)]/80">
            <Command.Empty className="py-6 text-center text-[var(--muted-fg)]">
              No matches.
            </Command.Empty>

            <Command.Group heading="Navigation">
              <PaletteItem
                onSelect={() => navigateAndClose("/")}
                icon={<Home className="size-4" />}
              >
                Go to Home
              </PaletteItem>
              <PaletteItem
                onSelect={() => navigateAndClose("/approvals")}
                icon={<CheckCircle2 className="size-4" />}
              >
                Go to Approvals
              </PaletteItem>
              <PaletteItem
                onSelect={() => navigateAndClose("/activity")}
                icon={<Activity className="size-4" />}
              >
                Go to Activity
              </PaletteItem>
              <PaletteItem
                onSelect={() => navigateAndClose("/settings")}
                icon={<Cog className="size-4" />}
              >
                Go to Settings
              </PaletteItem>
            </Command.Group>

            {pages.length > 0 && (
              <Command.Group heading="Pages">
                {pages.map((p) => (
                  <PaletteItem
                    key={p.id}
                    value={`page ${p.name} ${p.slug}`}
                    onSelect={() =>
                      navigateAndClose(
                        p.slug === "home" ? "/" : `/pages/${p.slug}`,
                      )
                    }
                    icon={<FileText className="size-4" />}
                  >
                    {p.name}
                    <span className="ml-2 text-[var(--muted-fg)] text-xs">
                      /{p.slug}
                    </span>
                  </PaletteItem>
                ))}
              </Command.Group>
            )}

            <Command.Group heading="Settings">
              {SETTINGS_PAGES.map((s) => (
                <PaletteItem
                  key={s.slug}
                  value={`settings ${s.name}`}
                  onSelect={() => navigateAndClose(`/settings/${s.slug}`)}
                  icon={<ShieldCheck className="size-4" />}
                >
                  {s.name}
                </PaletteItem>
              ))}
            </Command.Group>

            <Command.Group heading="Commands">
              <PaletteItem
                onSelect={toggleEdit}
                icon={<PencilLine className="size-4" />}
              >
                Toggle edit mode
              </PaletteItem>
              <PaletteItem
                onSelect={toggleDark}
                icon={
                  <>
                    <Moon className="size-4 dark:hidden" />
                    <Sun className="size-4 hidden dark:inline" />
                  </>
                }
              >
                Toggle dark mode
              </PaletteItem>
              <PaletteItem
                onSelect={() => void logout()}
                icon={<LogOut className="size-4" />}
              >
                Log out
              </PaletteItem>
            </Command.Group>

            {formattedActivity.length > 0 && (
              <Command.Group heading="Recent activity">
                {formattedActivity.map((row) => (
                  <PaletteItem
                    key={row.id}
                    value={`activity ${row.label} ${row.sub}`}
                    onSelect={() =>
                      navigateAndClose(`/activity?focus=${row.id}`)
                    }
                    icon={<Activity className="size-4" />}
                  >
                    <span className="font-mono text-xs">
                      #{row.id} {row.label}
                    </span>
                    {row.sub && (
                      <span className="ml-2 text-[var(--muted-fg)] text-xs">
                        {row.sub}
                      </span>
                    )}
                  </PaletteItem>
                ))}
              </Command.Group>
            )}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}

function PaletteItem({
  children,
  onSelect,
  icon,
  value,
}: {
  children: React.ReactNode;
  onSelect: () => void;
  icon?: React.ReactNode;
  value?: string;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-[var(--muted-fg)] transition-colors aria-selected:bg-[var(--accent-soft)] aria-selected:text-[var(--accent)]"
    >
      {icon}
      <span className="flex-1 flex items-center">{children}</span>
    </Command.Item>
  );
}
