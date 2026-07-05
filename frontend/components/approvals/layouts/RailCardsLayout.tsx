"use client";

import type { ApprovalLayoutProps } from "./shared";

/**
 * Rail Cards — a flat vertical list of the full `ApprovalCard`, each with its
 * family-colored rail + risk pip. The richest, lowest-risk default.
 */
export function RailCardsLayout({ rows, renderCard }: ApprovalLayoutProps) {
  return (
    <div className="flex flex-col gap-3">
      {rows.map((vm) => (
        <div key={vm.request.id}>{renderCard(vm.request)}</div>
      ))}
    </div>
  );
}
