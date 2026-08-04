"use client";

import Link from "next/link";

import { actionVerb, outcomeMeta } from "@/components/activity/activityMeta";
import { AgentBadge } from "@/components/agents/AgentBadge";
import { Badge } from "@/components/ui/Badge";
import {
  type ActionTarget,
  type ActivityLogRow,
  type Agent,
  type Module,
  type Page,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime, formatTimeOfDay } from "@/lib/time";

type ActivityRowProps = {
  row: ActivityLogRow;
  agentsById: Map<string, Agent>;
  modulesById: Map<string, Module>;
  pagesById: Map<string, Page>;
  actionTargetsById: Map<string, ActionTarget>;
  /** Include the calendar date in the time cell (used when day headers are off). */
  showDate?: boolean;
  onClick: () => void;
  /** Filter the feed to this actor id (from clicking the actor chip). */
  onActorClick?: (actorId: string) => void;
};

const shortDate = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

function resolveTarget(
  row: ActivityLogRow,
  modulesById: Map<string, Module>,
  pagesById: Map<string, Page>,
  actionTargetsById: Map<string, ActionTarget>,
): { label: string; context?: string; href?: string } {
  if (row.target_kind === "module" && row.target_id) {
    const mod = modulesById.get(row.target_id);
    const page = mod ? pagesById.get(mod.page_id) : undefined;
    const label = mod?.title?.trim() || mod?.type || payloadLabel(row) || row.target_id;
    if (page) {
      const href = page.slug === "home" ? "/" : `/pages/${page.slug}`;
      return { label, context: page.name, href };
    }
    return { label };
  }
  if (row.target_kind === "page" && row.target_id) {
    const p = pagesById.get(row.target_id);
    if (p) {
      const href = p.slug === "home" ? "/" : `/pages/${p.slug}`;
      return { label: p.name, href };
    }
    return { label: payloadLabel(row) ?? row.target_id };
  }
  if (row.target_kind === "action_target" && row.target_id) {
    const t = actionTargetsById.get(row.target_id);
    return { label: t?.name ?? row.target_id, href: "/settings/action-targets" };
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

/** Best-effort human label from the audit payload for deleted / unknown targets. */
function payloadLabel(row: ActivityLogRow): string | undefined {
  const p = row.payload_summary;
  if (!p) return undefined;
  for (const key of ["title", "name", "slug"]) {
    const v = p[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  return undefined;
}

export function ActivityRow({
  row,
  agentsById,
  modulesById,
  pagesById,
  actionTargetsById,
  showDate = false,
  onClick,
  onActorClick,
}: ActivityRowProps) {
  const target = resolveTarget(row, modulesById, pagesById, actionTargetsById);
  const outcome = outcomeMeta(row.outcome);
  const isAgent = row.actor_kind === "agent" && !!row.actor_id;
  const actorLabel =
    row.actor_id === "admin" ? "Admin" : `${row.actor_kind}${row.actor_id ? `:${row.actor_id}` : ""}`;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className="group flex w-full cursor-pointer items-stretch gap-3 px-4 text-left text-sm transition-colors hover:bg-[var(--muted)]/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]"
    >
      <span
        className="w-16 shrink-0 self-center font-mono text-xs tabular-nums text-[var(--muted-fg)]"
        title={formatDateTime(row.timestamp)}
      >
        {showDate && (
          <span className="block text-[10px] leading-tight text-[var(--muted-fg)]/70">
            {shortDate.format(new Date(row.timestamp))}
          </span>
        )}
        {formatTimeOfDay(row.timestamp)}
      </span>

      {/* Timeline rail: hairline through an outcome-colored dot. */}
      <span aria-hidden className="flex w-3 shrink-0 flex-col items-center">
        <span className="w-px flex-1 bg-[var(--border)]" />
        <span
          className={cn("my-1 size-2 shrink-0 rounded-full", outcome.dotClass)}
          title={outcome.label}
        />
        <span className="w-px flex-1 bg-[var(--border)]" />
      </span>

      <span className="flex min-w-0 flex-1 flex-col justify-center gap-0.5 py-2.5">
        <span className="flex min-w-0 items-center gap-2">
          {isAgent ? (
            <ClickableActor
              onActorClick={onActorClick ? () => onActorClick(row.actor_id!) : undefined}
            >
              <AgentBadge
                agentId={row.actor_id}
                displayName={agentsById.get(row.actor_id!)?.display_name}
              />
            </ClickableActor>
          ) : (
            <ClickableActor
              onActorClick={
                onActorClick && row.actor_id ? () => onActorClick(row.actor_id!) : undefined
              }
            >
              <Badge tone="neutral">{actorLabel}</Badge>
            </ClickableActor>
          )}
          <span className="shrink-0 text-[var(--muted-fg)]">{actionVerb(row.action_type)}</span>
          <span className="min-w-0 truncate font-medium">
            {target.href ? (
              <Link
                href={target.href}
                onClick={(e) => e.stopPropagation()}
                className="hover:underline underline-offset-2"
              >
                {target.label}
              </Link>
            ) : (
              target.label
            )}
            {target.context && (
              <span className="ml-1.5 font-normal text-[var(--muted-fg)]">
                · {target.context}
              </span>
            )}
          </span>
        </span>
        {row.error_detail && (
          <span className="truncate font-mono text-xs text-[var(--danger)]">
            {row.error_detail}
          </span>
        )}
      </span>

      {row.outcome !== "applied" && (
        <span
          className={cn(
            "shrink-0 self-center text-xs font-medium lowercase",
            outcome.textClass,
          )}
        >
          {outcome.label}
        </span>
      )}
      <span className="hidden shrink-0 self-center font-mono text-[11px] text-[var(--muted-fg)]/60 lg:block">
        {row.action_type}
      </span>
    </div>
  );
}

/** Wraps an actor chip; when a filter callback is provided, clicking it filters
 * the feed to that actor instead of opening the row detail. */
function ClickableActor({
  onActorClick,
  children,
}: {
  onActorClick?: () => void;
  children: React.ReactNode;
}) {
  if (!onActorClick) return <span className="shrink-0">{children}</span>;
  return (
    <button
      type="button"
      title="Filter to this actor"
      onClick={(e) => {
        e.stopPropagation();
        onActorClick();
      }}
      className="shrink-0 rounded-full transition-opacity hover:opacity-75 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
    >
      {children}
    </button>
  );
}
