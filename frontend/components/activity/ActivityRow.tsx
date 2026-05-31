"use client";

import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import Link from "next/link";

import { AgentBadge } from "@/components/agents/AgentBadge";
import { Badge } from "@/components/ui/Badge";
import {
  type ActivityLogRow,
  type Agent,
  type Module,
  type Page,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime, relativeTime } from "@/lib/time";

type ActivityRowProps = {
  row: ActivityLogRow;
  agentsById: Map<string, Agent>;
  modulesById: Map<string, Module>;
  pagesById: Map<string, Page>;
  onClick: () => void;
};

function outcomeIcon(outcome: string) {
  switch (outcome) {
    case "applied":
      return <CheckCircle2 className="size-4 text-green-500" />;
    case "auto_approved":
      return <ShieldCheck className="size-4 text-green-500" />;
    case "queued":
      return <Clock className="size-4 text-amber-500" />;
    case "denied":
      return <XCircle className="size-4 text-[var(--danger)]" />;
    case "error":
      return <AlertCircle className="size-4 text-[var(--danger)]" />;
    default:
      return <ArrowRight className="size-4 text-[var(--muted-fg)]" />;
  }
}

function resolveTargetLink(
  row: ActivityLogRow,
  modulesById: Map<string, Module>,
  pagesById: Map<string, Page>,
): { label: string; href?: string } {
  if (row.target_kind === "module" && row.target_id) {
    const mod = modulesById.get(row.target_id);
    const page = mod ? pagesById.get(mod.page_id) : undefined;
    const label = mod?.title ?? mod?.type ?? row.target_id;
    if (page) {
      const href = page.slug === "home" ? "/" : `/pages/${page.slug}`;
      return { label, href };
    }
    return { label };
  }
  if (row.target_kind === "page" && row.target_id) {
    const p = pagesById.get(row.target_id);
    if (p) {
      const href = p.slug === "home" ? "/" : `/pages/${p.slug}`;
      return { label: p.name, href };
    }
    return { label: row.target_id };
  }
  if (row.target_kind === "approval_rule" && row.target_id) {
    return {
      label: `rule ${row.target_id.slice(-6)}`,
      href: `/settings/rules?id=${row.target_id}`,
    };
  }
  if (row.target_id) return { label: row.target_id };
  return { label: "—" };
}

export function ActivityRow({
  row,
  agentsById,
  modulesById,
  pagesById,
  onClick,
}: ActivityRowProps) {
  const target = resolveTargetLink(row, modulesById, pagesById);
  const actor =
    row.actor_kind === "agent" && row.actor_id
      ? (
          <AgentBadge
            agentId={row.actor_id}
            displayName={agentsById.get(row.actor_id)?.display_name}
          />
        )
      : (
          <Badge className="bg-[var(--muted)] text-[var(--fg)] border-[var(--border)]">
            {row.actor_kind}
            {row.actor_id ? `:${row.actor_id}` : ""}
          </Badge>
        );

  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-3 border-b border-[var(--border)] px-3 py-2 text-left text-sm hover:bg-[var(--muted)]"
    >
      <span
        className="shrink-0 text-xs text-[var(--muted-fg)] w-20"
        title={formatDateTime(row.timestamp)}
      >
        {relativeTime(row.timestamp)}
      </span>
      <span className="shrink-0">{actor}</span>
      <Badge className="bg-[var(--bg)] border-[var(--border)] text-[var(--muted-fg)]">
        {row.action_type}
      </Badge>
      <span className={cn("flex-1 min-w-0 truncate", target.href && "underline-offset-2")}>
        {target.href ? (
          <Link
            href={target.href}
            onClick={(e) => e.stopPropagation()}
            className="hover:underline"
          >
            {target.label}
          </Link>
        ) : (
          target.label
        )}
      </span>
      <span className="shrink-0">{outcomeIcon(row.outcome)}</span>
    </button>
  );
}
