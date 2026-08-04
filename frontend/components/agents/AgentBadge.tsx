import { Bot } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";

type AgentBadgeProps = {
  agentId?: string | null;
  displayName?: string | null;
  className?: string;
};

/** Small chip used to label an actor in queues + activity rows. */
export function AgentBadge({ agentId, displayName, className }: AgentBadgeProps) {
  const label = displayName ?? agentId ?? "Unknown agent";
  return (
    <Badge
      tone="neutral"
      className={cn("gap-1 text-[var(--fg)]", className)}
      title={agentId ?? undefined}
    >
      <Bot className="size-3" />
      <span className="truncate max-w-[12rem]">{label}</span>
    </Badge>
  );
}
