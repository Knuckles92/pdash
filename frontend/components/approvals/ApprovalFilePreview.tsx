"use client";

import { FileText, Image as ImageIcon } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import type { FilePreview } from "@/lib/api";
import { humanizeBytes } from "@/lib/bytes";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">{label}</span>
      <span className="break-all text-[var(--fg)]">{value}</span>
    </div>
  );
}

export function ApprovalFilePreview({ preview }: { preview: FilePreview }) {
  const size = humanizeBytes(preview.size_bytes);
  const Icon = preview.kind === "image" ? ImageIcon : FileText;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <Icon className="size-3.5 text-[var(--muted-fg)]" />
        <span className="font-medium text-sm">{preview.display_name ?? preview.inbox_name ?? "File"}</span>
        {preview.kind && (
          <Badge className="bg-[var(--muted)] text-[var(--fg)] border-[var(--border)]">
            {preview.kind}
          </Badge>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        {preview.inbox_name && <Field label="Dropped as" value={preview.inbox_name} />}
        {preview.mime && <Field label="Type" value={preview.mime} />}
        {size && <Field label="Size" value={size} />}
        {preview.page && <Field label="For page" value={preview.page.name} />}
        {preview.purpose && <Field label="Purpose" value={preview.purpose} />}
        {preview.sha256 && <Field label="SHA-256" value={preview.sha256.slice(0, 16)} />}
      </div>

      <p className="mt-3 text-xs text-[var(--muted-fg)]">
        The file is still in the inbox; its bytes are re-verified against this checksum when approved.
      </p>
    </div>
  );
}
