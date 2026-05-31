"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import { useOrphanCount } from "@/lib/hooks/useOrphanCount";

const TABS = [
  { href: "/settings/agents", label: "Agents" },
  { href: "/settings/pages", label: "Pages" },
  { href: "/settings/rules", label: "Rules" },
  { href: "/settings/action-targets", label: "Action targets" },
  { href: "/settings/iframe-allowlist", label: "Iframe allowlist" },
  { href: "/settings/files", label: "Files", badge: "orphans" as const },
];

export function SettingsTabs() {
  const pathname = usePathname() ?? "";
  const { count: orphanCount } = useOrphanCount();
  return (
    <nav className="flex items-center gap-1 border-b border-[var(--border)]">
      {TABS.map((t) => {
        const active = pathname.startsWith(t.href);
        const showBadge = "badge" in t && t.badge === "orphans" && orphanCount > 0;
        return (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 -mb-px",
              active
                ? "border-[var(--accent)] text-[var(--fg)] font-medium"
                : "border-transparent text-[var(--muted-fg)] hover:text-[var(--fg)]",
            )}
          >
            {t.label}
            {showBadge && (
              <Badge
                className="border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
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
