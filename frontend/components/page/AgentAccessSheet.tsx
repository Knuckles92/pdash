"use client";

import { Bot, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Sheet } from "@/components/ui/Sheet";
import type { Page, PageAgentAccessItem } from "@/lib/api";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/cn";

type AgentAccessSheetProps = {
  page: Page;
  open: boolean;
  onClose: () => void;
};

const LEVELS = [
  { value: "default", label: "Default" },
  { value: "free", label: "Full access" },
  { value: "blocked", label: "Blocked" },
] as const;

type Level = (typeof LEVELS)[number]["value"];

function successMessage(level: Level, agentName: string, pageName: string): string {
  switch (level) {
    case "free":
      return `${agentName} can now edit "${pageName}" without approvals`;
    case "blocked":
      return `${agentName} is blocked from changing "${pageName}"`;
    default:
      return `${agentName} follows your approval rules on "${pageName}"`;
  }
}

/**
 * Per-page agent access panel, opened from the page actions (…) menu.
 *
 * A quick-toggle layer over approval rules: each agent gets Default /
 * Full access / Blocked for this page; the backend persists the choice as a
 * managed set of agent+page-scoped rules. Anything more surgical lives in
 * Settings → Rules (linked from the footer).
 */
export function AgentAccessSheet({ page, open, onClose }: AgentAccessSheetProps) {
  const [items, setItems] = useState<PageAgentAccessItem[] | null>(null);
  const [savingAgentId, setSavingAgentId] = useState<string | null>(null);
  const rulesHref = `/settings/rules?page_id=${encodeURIComponent(page.id)}`;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setItems(null);
    api
      .getPageAgentAccess(page.id)
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch((err) => {
        if (!cancelled) {
          toast.error(errorMessage(err, "Could not load agent access"));
          setItems([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, page.id]);

  async function setLevel(item: PageAgentAccessItem, level: Level) {
    if (savingAgentId) return;
    if (item.access === level) return;
    setSavingAgentId(item.agent_id);
    try {
      const updated = await api.setPageAgentAccess(page.id, item.agent_id, level);
      setItems(
        (prev) =>
          prev?.map((it) => (it.agent_id === updated.agent_id ? updated : it)) ?? prev,
      );
      toast.success(successMessage(level, item.display_name, page.name));
    } catch (err) {
      toast.error(errorMessage(err, "Update failed"));
    } finally {
      setSavingAgentId(null);
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Agent access"
      description={`What agents can change on "${page.name}" without asking.`}
      footer={
        <Link
          href={rulesHref}
          onClick={onClose}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--accent)] hover:underline"
        >
          <SlidersHorizontal className="size-3.5" />
          Advanced rules for this page
        </Link>
      }
    >
      <div className="space-y-4">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--muted)]/40 px-3.5 py-3 text-xs leading-relaxed text-[var(--muted-fg)]">
          <p>
            <span className="font-medium text-[var(--fg)]">Default</span> — your approval
            rules decide: an agent&apos;s edits to its own modules apply instantly,
            everything else asks first.
          </p>
          <p>
            <span className="font-medium text-[var(--fg)]">Full access</span> — the agent
            can create, edit, and remove modules on this page without approval.
          </p>
          <p>
            <span className="font-medium text-[var(--fg)]">Blocked</span> — every module
            change the agent proposes on this page is denied.
          </p>
        </div>

        {items === null ? (
          <p className="px-1 py-6 text-center text-sm text-[var(--muted-fg)]">
            Loading agents…
          </p>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Bot className="size-5" />}
            title="No agents yet"
            hint="Create or approve an agent in Settings → Agents, then manage its access here."
          />
        ) : (
          <ul className="divide-y divide-[var(--border)] rounded-xl border border-[var(--border)]">
            {items.map((item) => (
              <li key={item.agent_id} className="px-3.5 py-3">
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-[var(--fg)]">
                        {item.display_name}
                      </span>
                      {item.status === "disabled" && (
                        <Badge tone="neutral">disabled</Badge>
                      )}
                      {item.access === "custom" && (
                        <Badge tone="warning">custom</Badge>
                      )}
                    </div>
                    <p className="mt-0.5 font-mono text-xs text-[var(--muted-fg)]">
                      {item.module_count === 0
                        ? "no modules on this page"
                        : `${item.module_count} module${item.module_count === 1 ? "" : "s"} on this page`}
                    </p>
                  </div>
                  <div
                    className="inline-flex shrink-0 rounded-lg border border-[var(--border)] bg-[var(--muted)]/40 p-0.5"
                    role="radiogroup"
                    aria-label={`Access level for ${item.display_name}`}
                  >
                    {LEVELS.map((level) => {
                      const selected = item.access === level.value;
                      return (
                        <button
                          key={level.value}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          disabled={savingAgentId !== null}
                          onClick={() => setLevel(item, level.value)}
                          className={cn(
                            "rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-60",
                            selected
                              ? level.value === "blocked"
                                ? "bg-[var(--danger-soft)] text-[var(--danger)]"
                                : level.value === "free"
                                  ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                                  : "bg-[var(--card)] text-[var(--fg)] shadow-sm"
                              : "text-[var(--muted-fg)] hover:text-[var(--fg)]",
                          )}
                        >
                          {level.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
                {item.access === "custom" && (
                  <p className="mt-2 text-xs text-[var(--muted-fg)]">
                    This agent&apos;s rules for this page were customized. Picking a level
                    here resets the basics; advanced rules are kept.
                  </p>
                )}
                {item.custom_rule_count > 0 && (
                  <p className="mt-1 text-xs text-[var(--muted-fg)]">
                    <Link
                      href={rulesHref}
                      onClick={onClose}
                      className="text-[var(--accent)] hover:underline"
                    >
                      +{item.custom_rule_count} advanced rule
                      {item.custom_rule_count === 1 ? "" : "s"}
                    </Link>{" "}
                    also apply on this page.
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Sheet>
  );
}
