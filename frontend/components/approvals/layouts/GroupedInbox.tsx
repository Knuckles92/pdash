"use client";

import { Check, ChevronDown, ChevronRight, X } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

import {
  AgentAvatar,
  CompactRow,
  groupRowsByAgent,
  type ApprovalLayoutProps,
} from "./shared";

/**
 * Agent-grouped, collapsible inbox of compact rows. Clicking a row expands it
 * into the full `ApprovalCard` (with previews + rule actions) in place. Shared
 * by the Triage Inbox and Command Center layouts.
 */
export function GroupedInbox({
  rows,
  onApprove,
  onDeny,
  onApproveMany,
  onDenyMany,
  onWantDetail,
  renderCard,
}: ApprovalLayoutProps) {
  const groups = groupRowsByAgent(rows);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [expandedId, setExpandedId] = useState<string | null>(null);

  function toggleGroup(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleRow(id: string) {
    setExpandedId((prev) => {
      if (prev === id) return null;
      onWantDetail(id);
      return id;
    });
  }

  return (
    <div className="flex flex-col gap-2">
      {groups.map((group) => {
        const isCollapsed = collapsed.has(group.key);
        const ids = group.rows.map((r) => r.request.id);
        return (
          <div
            key={group.key}
            className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--card)]"
          >
            <div className="flex items-center gap-2 border-b border-[var(--border)] px-2 py-1.5">
              <button
                type="button"
                onClick={() => toggleGroup(group.key)}
                className="inline-flex size-6 items-center justify-center rounded text-[var(--muted-fg)] hover:bg-[var(--muted)]"
                aria-label={isCollapsed ? "Expand" : "Collapse"}
              >
                {isCollapsed ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}
              </button>
              <AgentAvatar agentId={group.agentId} name={group.label} size="sm" />
              <span className="font-medium">{group.label}</span>
              {group.kind === "new" && (
                <span className="rounded-full border border-[var(--border)] bg-[var(--muted)] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">
                  new
                </span>
              )}
              <span className="rounded-full bg-[var(--muted)] px-1.5 text-xs text-[var(--muted-fg)]">
                {group.rows.length}
              </span>
              <div className="ml-auto flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onApproveMany(ids)}
                  className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium text-[var(--success)] hover:bg-[var(--success)]/10"
                >
                  <Check className="size-3.5" /> all
                </button>
                <button
                  type="button"
                  onClick={() => onDenyMany(ids)}
                  className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium text-[var(--danger)] hover:bg-[var(--danger)]/10"
                >
                  <X className="size-3.5" /> all
                </button>
              </div>
            </div>
            {!isCollapsed && (
              <div className="flex flex-col gap-0.5 p-1.5">
                {group.rows.map((vm) =>
                  expandedId === vm.request.id ? (
                    <div key={vm.request.id} className="py-1">
                      {renderCard(vm.request, { defaultExpanded: true })}
                    </div>
                  ) : (
                    <CompactRow
                      key={vm.request.id}
                      vm={vm}
                      onClick={() => toggleRow(vm.request.id)}
                      onApprove={() => onApprove(vm.request.id, false)}
                      onDeny={() => onDeny(vm.request.id, false)}
                    />
                  ),
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
