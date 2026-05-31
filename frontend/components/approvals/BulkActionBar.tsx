"use client";

import { Check, X } from "lucide-react";

import { Button } from "@/components/ui/Button";

type BulkActionBarProps = {
  count: number;
  busy?: boolean;
  onApproveAll: () => void;
  onDenyAll: () => void;
  onClear: () => void;
};

export function BulkActionBar({
  count,
  busy,
  onApproveAll,
  onDenyAll,
  onClear,
}: BulkActionBarProps) {
  if (count === 0) return null;
  return (
    <div
      className="fixed left-1/2 -translate-x-1/2 bottom-20 md:bottom-6 z-30 w-[calc(100%-1rem)] max-w-xl rounded-full border border-[var(--border)] bg-[var(--card)] shadow-lg px-4 py-2 flex items-center gap-3 animate-in slide-in-from-bottom-4"
      role="region"
      aria-label="Bulk actions"
    >
      <span className="text-sm font-medium">{count} selected</span>
      <Button size="sm" disabled={busy} onClick={onApproveAll}>
        <Check className="size-4" /> Approve all
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={onDenyAll}
      >
        <X className="size-4" /> Deny all
      </Button>
      <Button size="sm" variant="ghost" onClick={onClear} className="ml-auto">
        Clear
      </Button>
    </div>
  );
}
