"use client";

import { AlertTriangle, Clock } from "lucide-react";

import { cn } from "@/lib/cn";

import { GroupedInbox } from "./GroupedInbox";
import {
  FAMILY_ORDER,
  FAMILY_STYLES,
  familyCounts,
  type ActionFamily,
  type ApprovalLayoutProps,
  type ApprovalRowVM,
} from "./shared";

/** Command Center — bento stat tiles over the grouped queue. */
export function CommandCenterLayout(props: ApprovalLayoutProps) {
  const { rows } = props;
  const counts = familyCounts(rows);
  const needsLook = rows.filter((r) => r.destructive).length;
  const oldest = oldestRow(rows);
  const activeAgents = new Set(rows.map((r) => r.request.agent_id ?? "__new__")).size;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {FAMILY_ORDER.map((family) => (
          <FamilyTile key={family} family={family} count={counts[family]} />
        ))}
        <div className="col-span-2 flex items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 sm:col-span-1">
          <AlertTriangle className="size-5 text-amber-600 dark:text-amber-400" />
          <div>
            <div className="text-xl font-semibold tabular-nums">{needsLook}</div>
            <div className="text-xs text-amber-700 dark:text-amber-300">need a look</div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--muted-fg)]">
        {oldest && (
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3.5" /> oldest: {oldest.target} ({oldest.age})
          </span>
        )}
        <span>{activeAgents} agents active</span>
        <span>{rows.length} total pending</span>
      </div>

      <GroupedInbox {...props} />
    </div>
  );
}

function oldestRow(rows: ApprovalRowVM[]): ApprovalRowVM | null {
  if (rows.length === 0) return null;
  return rows.reduce((oldest, r) =>
    r.request.created_at < oldest.request.created_at ? r : oldest,
  );
}

function FamilyTile({ family, count }: { family: ActionFamily; count: number }) {
  const st = FAMILY_STYLES[family];
  const Icon = st.icon;
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border p-3",
        count > 0 ? st.border : "border-[var(--border)]",
        count > 0 ? st.tint : "opacity-50",
      )}
    >
      <Icon className={cn("size-5", st.text)} />
      <div>
        <div className="text-xl font-semibold tabular-nums">{count}</div>
        <div className={cn("text-xs capitalize", st.text)}>{family}</div>
      </div>
    </div>
  );
}
