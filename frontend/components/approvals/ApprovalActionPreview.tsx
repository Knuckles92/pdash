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
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <Zap className="size-3.5 text-[var(--muted-fg)]" />
        <span className="font-medium text-sm">{target.name}</span>
        <Badge className="bg-[var(--muted)] text-[var(--fg)] border-[var(--border)]">
          {KIND_LABEL[target.kind]}
        </Badge>
        <Badge className="bg-[var(--muted)] text-[var(--fg)] border-[var(--border)]">
          {target.mode}
        </Badge>
        {!target.enabled && (
          <Badge className="bg-[var(--danger)]/15 text-[var(--danger)] border-[var(--danger)]/30">
            Disabled
          </Badge>
        )}
      </div>

      {destination && (
        <div className="mb-2">
          <div className="text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">
            Will call
          </div>
          <code className="mt-1 block break-all rounded-md bg-[var(--muted)] px-2 py-1 text-[11px]">
            {destination}
          </code>
        </div>
      )}

      <div>
        <div className="text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">
          Payload{uses_target_default ? " (target default)" : ""}
        </div>
        {payloadKeys.length === 0 ? (
          <p className="mt-1 text-xs text-[var(--muted-fg)]">Empty payload.</p>
        ) : (
          <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-[var(--muted)] p-2 text-[11px] leading-snug">
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
