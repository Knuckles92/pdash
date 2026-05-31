import { Bot } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";

type AgentBadgeProps = {
  agentId: string;
  displayName?: string | null;
  className?: string;
};

/** Small chip used to label an actor in queues + activity rows. */
export function AgentBadge({ agentId, displayName, className }: AgentBadgeProps) {
  const label = displayName ?? agentId;
  return (
    <Badge
      className={cn(
        "bg-[var(--muted)] text-[var(--fg)] border-[var(--border)] gap-1",
        className,
      )}
      title={agentId}
    >
      <Bot className="size-3" />
      <span className="truncate max-w-[12rem]">{label}</span>
    </Badge>
  );
}
