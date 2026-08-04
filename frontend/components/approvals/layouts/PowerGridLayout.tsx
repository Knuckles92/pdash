"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";

import {
  FAMILY_ORDER,
  FAMILY_STYLES,
  FamilyIcon,
  MiniDecide,
  RiskBadge,
  actionTypeLabel,
  type ApprovalLayoutProps,
  type ApprovalRowVM,
} from "./shared";

type SortKey = "agent" | "family" | "age";
type SortDir = "asc" | "desc";

/** Power Grid — max-density sortable table with bulk select. */
export function PowerGridLayout({
  rows,
  selectedIds,
  onToggleSelect,
  onApprove,
  onDeny,
  onWantDetail,
  renderCard,
}: ApprovalLayoutProps) {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "age", dir: "asc" });
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const sorted = useMemo(() => sortRows(rows, sort.key, sort.dir), [rows, sort]);

  function toggleSort(key: SortKey) {
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" },
    );
  }

  function toggleRow(id: string) {
    setExpandedId((prev) => {
      if (prev === id) return null;
      onWantDetail(id);
      return id;
    });
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--card)]">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] bg-[var(--muted)]/60 text-left text-xs font-medium uppercase tracking-wide text-[var(--muted-fg)]">
            <th className="w-9 px-2 py-2" />
            <SortTh label="Action" active={sort.key === "family"} dir={sort.dir} onClick={() => toggleSort("family")} />
            <th className="px-2 py-2 font-medium">Target</th>
            <SortTh label="Agent" active={sort.key === "agent"} dir={sort.dir} onClick={() => toggleSort("agent")} />
            <SortTh label="Age" active={sort.key === "age"} dir={sort.dir} onClick={() => toggleSort("age")} />
            <th className="w-20 px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((vm) => {
            const st = FAMILY_STYLES[vm.family];
            const isExpanded = expandedId === vm.request.id;
            return (
              <FragmentRow key={vm.request.id}>
                <tr
                  onClick={() => toggleRow(vm.request.id)}
                  className={cn(
                    "cursor-pointer border-b border-[var(--border)] transition-colors hover:bg-[var(--muted)]/60",
                    isExpanded && "bg-[var(--accent-soft)]/50",
                  )}
                >
                  <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label="Select for bulk action"
                      checked={selectedIds.has(vm.request.id)}
                      onChange={() => onToggleSelect(vm.request.id)}
                      className="size-4 accent-[var(--accent)]"
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <span className="inline-flex items-center gap-1.5">
                      <span className={cn("h-4 w-1 shrink-0 rounded-full", st.rail)} />
                      <FamilyIcon family={vm.family} className={st.text} />
                      <span className="font-medium">{actionTypeLabel(vm.request.action_type)}</span>
                    </span>
                  </td>
                  <td className="max-w-[16rem] truncate px-2 py-1.5 font-mono text-xs text-[var(--muted-fg)]" title={vm.target}>
                    {vm.target}
                  </td>
                  <td className="px-2 py-1.5">{vm.agentLabel}</td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-xs tabular-nums text-[var(--muted-fg)]">
                    <span className="inline-flex items-center gap-1.5">
                      {vm.age}
                      <RiskBadge label={vm.risk} />
                    </span>
                  </td>
                  <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                    <MiniDecide
                      onApprove={() => onApprove(vm.request.id, false)}
                      onDeny={() => onDeny(vm.request.id, false)}
                    />
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="border-b border-[var(--border)] bg-[var(--bg)]">
                    <td colSpan={6} className="p-3">
                      {renderCard(vm.request, { defaultExpanded: true })}
                    </td>
                  </tr>
                )}
              </FragmentRow>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** A table fragment wrapper so a row + its expansion share a key. */
function FragmentRow({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

function SortTh({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  return (
    <th className="px-2 py-2 font-medium">
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 rounded transition-colors hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
          active && "text-[var(--accent)]",
        )}
      >
        {label}
        {active &&
          (dir === "asc" ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />)}
      </button>
    </th>
  );
}

function sortRows(rows: ApprovalRowVM[], key: SortKey, dir: SortDir): ApprovalRowVM[] {
  const sign = dir === "asc" ? 1 : -1;
  const copy = rows.slice();
  copy.sort((a, b) => {
    let cmp = 0;
    if (key === "agent") {
      cmp = a.agentLabel.localeCompare(b.agentLabel);
    } else if (key === "family") {
      cmp = FAMILY_ORDER.indexOf(a.family) - FAMILY_ORDER.indexOf(b.family);
    } else {
      // "age" — oldest first when ascending (earlier timestamp sorts first).
      cmp = a.request.created_at < b.request.created_at ? -1 : a.request.created_at > b.request.created_at ? 1 : 0;
    }
    return cmp * sign;
  });
  return copy;
}
