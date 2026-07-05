"use client";

import { Zap } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import type { ActionPreview } from "@/lib/api";

const KIND_LABEL: Record<ActionPreview["target"]["kind"], string> = {
  webhook: "Webhook",
  local_script: "Local script",
  mcp_tool: "MCP tool",
  agent_message: "Agent message",
};

export function ApprovalActionPreview({ preview }: { preview: ActionPreview }) {
  const { target, destination, payload, uses_target_default } = preview;
  const payloadKeys = Object.keys(payload ?? {});

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <Zap className="size-3.5 text-[var(--muted-fg)]" />
        <span className="text-sm font-semibold tracking-tight">{target.name}</span>
        <Badge tone="neutral">{KIND_LABEL[target.kind]}</Badge>
        <Badge tone="neutral">{target.mode}</Badge>
        {!target.enabled && <Badge tone="danger">Disabled</Badge>}
      </div>

      {destination && (
        <div className="mb-3">
          <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
            Will call
          </div>
          <code className="mt-1 block break-all rounded-lg bg-[var(--muted)] px-2.5 py-1.5 font-mono text-[11px]">
            {destination}
          </code>
        </div>
      )}

      <div>
        <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
          Payload{uses_target_default ? " (target default)" : ""}
        </div>
        {payloadKeys.length === 0 ? (
          <p className="mt-1 text-xs text-[var(--muted-fg)]">Empty payload.</p>
        ) : (
          <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-[var(--muted)] p-3 font-mono text-[11px] leading-snug">
            {JSON.stringify(payload, null, 2)}
          </pre>
        )}
      </div>

      {!target.enabled && (
        <p className="mt-2 text-xs text-[var(--danger)]">
          This target is disabled — firing it will fail unless it is re-enabled first.
        </p>
      )}
    </div>
  );
}
