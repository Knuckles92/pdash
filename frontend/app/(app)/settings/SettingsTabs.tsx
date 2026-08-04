"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import { useOrphanCount } from "@/lib/hooks/useOrphanCount";

const TABS = [
  { href: "/settings/agents", label: "Agents" },
  { href: "/settings/mcp", label: "MCP" },
  { href: "/settings/pages", label: "Pages" },
  { href: "/settings/rules", label: "Rules" },
  { href: "/settings/action-targets", label: "Action targets" },
  { href: "/settings/iframe-allowlist", label: "Iframe allowlist" },
  { href: "/settings/files", label: "Files", badge: "orphans" as const },
  { href: "/settings/help", label: "Help" },
];

export function SettingsTabs() {
  const pathname = usePathname() ?? "";
  const { count: orphanCount } = useOrphanCount();
  return (
    <nav className="flex items-center gap-1 overflow-x-auto border-b border-[var(--border)]">
      {TABS.map((t) => {
        const active = pathname.startsWith(t.href);
        const badge = "badge" in t ? t.badge : undefined;
        const orphanBadge = badge === "orphans" && orphanCount > 0;
        return (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-2 text-sm border-b-2 -mb-px transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
              active
                ? "border-[var(--accent)] font-medium text-[var(--accent)]"
                : "border-transparent text-[var(--muted-fg)] hover:border-[var(--border-strong)] hover:text-[var(--fg)]",
            )}
          >
            {t.label}
            {orphanBadge && (
              <Badge
                tone="warning"
                title={`${orphanCount} file${orphanCount === 1 ? "" : "s"} need attention`}
              >
                {orphanCount}
              </Badge>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
