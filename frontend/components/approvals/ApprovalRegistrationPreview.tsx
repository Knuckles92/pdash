"use client";

import { UserPlus } from "lucide-react";

import type { RegistrationPreview } from "@/lib/api";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">{label}</span>
      <span className="break-words text-[var(--fg)]">{value}</span>
    </div>
  );
}

export function ApprovalRegistrationPreview({ preview }: { preview: RegistrationPreview }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <UserPlus className="size-3.5 text-[var(--muted-fg)]" />
        <span className="font-medium text-sm">
          {preview.requested_name ?? "New agent"}
        </span>
      </div>

      <div className="grid gap-y-2 text-xs">
        {preview.rationale && <Field label="Rationale" value={preview.rationale} />}
        {preview.description && <Field label="Description" value={preview.description} />}
        {preview.client_hint && <Field label="Client" value={preview.client_hint} />}
      </div>

      <p className="mt-3 text-xs text-[var(--muted-fg)]">
        Approving lets the agent retrieve its API key via MCP — no key is shown here.
      </p>
    </div>
  );
}
