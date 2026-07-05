"use client";

import { ChevronLeft } from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

import { CompactRow, type ApprovalLayoutProps } from "./shared";

/**
 * Master–Detail — grouped/flat list on the left, rich detail pane on the right.
 * Wide screens show both; narrow screens push the list aside to the detail.
 */
export function MasterDetailLayout({
  rows,
  onApprove,
  onDeny,
  onWantDetail,
  renderCard,
}: ApprovalLayoutProps) {
  const [selectedId, setSelectedId] = useState<string | null>(rows[0]?.request.id ?? null);

  // Keep the selection valid as rows are approved/denied away, and prefetch
  // the selected request's preview so the pane never sits on a spinner.
  useEffect(() => {
    if (rows.length === 0) {
      if (selectedId !== null) setSelectedId(null);
      return;
    }
    const valid = rows.some((r) => r.request.id === selectedId);
    const targetId = valid ? selectedId! : rows[0]!.request.id;
    if (!valid) setSelectedId(targetId);
    onWantDetail(targetId);
  }, [rows, selectedId, onWantDetail]);

  function select(id: string) {
    setSelectedId(id);
    onWantDetail(id);
  }

  const selected = rows.find((r) => r.request.id === selectedId) ?? null;

  return (
    <div className="md:grid md:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] md:gap-4">
      {/* List — hidden on mobile once a row is open. */}
      <div
        className={cn(
          "flex-col gap-0.5 rounded-xl border border-[var(--border)] bg-[var(--card)] p-2 shadow-[var(--shadow-sm)]",
          selected ? "hidden md:flex" : "flex",
        )}
      >
        {rows.map((vm) => (
          <CompactRow
            key={vm.request.id}
            vm={vm}
            showAgent
            active={vm.request.id === selectedId}
            onClick={() => select(vm.request.id)}
            onApprove={() => onApprove(vm.request.id, false)}
            onDeny={() => onDeny(vm.request.id, false)}
          />
        ))}
      </div>

      {/* Detail pane. */}
      <div className={cn(selected ? "block" : "hidden md:block")}>
        {selected ? (
          <>
            <button
              type="button"
              onClick={() => setSelectedId(null)}
              className="mb-2 inline-flex items-center gap-1 rounded-lg text-sm text-[var(--muted-fg)] transition-colors hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] md:hidden"
            >
              <ChevronLeft className="size-4" /> Back to list
            </button>
            {renderCard(selected.request, { defaultExpanded: true })}
          </>
        ) : (
          <div className="flex h-full min-h-40 items-center justify-center rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--card)]/60 text-sm text-[var(--muted-fg)]">
            Select a request to review
          </div>
        )}
      </div>
    </div>
  );
}
