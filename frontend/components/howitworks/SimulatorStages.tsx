"use client";

import {
  ArrowRight,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  ShieldCheck,
  ShieldX,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AgentBadge } from "@/components/agents/AgentBadge";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { severityChipClass } from "@/lib/modules/severity";
import type { Severity } from "@/lib/modules/types";

import { OUTCOMES, outcomeById, toneTint, type OutcomeId, type Tone } from "./simulatorModel";

/**
 * The four demo panels behind the CoreFlowSimulator stepper. Each is a static,
 * hand-built look-alike of a real surface (an MCP tool call, the rule match, an
 * ApprovalCard, the dashboard) — deliberately NOT importing the live components
 * (ApprovalCard/ActivityRow/ModuleHost), which are data-bound. They reuse the
 * real primitives (Card, Badge, AgentBadge, severityChipClass) so the shapes
 * match production. See ApprovalCard.tsx / KeyValueModule.tsx / ModuleHost.tsx.
 */

// ── Step 1: the agent proposes ──────────────────────────────────────────────

export function McpCallStage() {
  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--muted)]">
        <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[var(--card)] px-3 py-2">
          <span className="flex gap-1.5" aria-hidden>
            <span className="size-2.5 rounded-full bg-[var(--danger)]/50" />
            <span className="size-2.5 rounded-full bg-[var(--warning)]/50" />
            <span className="size-2.5 rounded-full bg-[var(--success)]/50" />
          </span>
          <AgentBadge agentId="agt_ops-bot" displayName="ops-bot" />
          <span className="ml-auto text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
            MCP · tool call
          </span>
        </div>
        <pre className="overflow-x-auto px-4 py-3 font-mono text-[11px] leading-relaxed text-[var(--fg)]">
          {`→ update_module({
    module_id: "mod_7Q4F…",
    data: { fields: [
      { key: "Disk", value: 81, unit: "%", severity: "warning" }
    ] }
  })`}
          <span
            aria-hidden
            className="hiw-caret ml-0.5 inline-block h-[1em] w-[2px] translate-y-0.5 bg-[var(--accent)] align-middle"
          />
        </pre>
      </div>
      <p className="text-xs leading-relaxed text-[var(--muted-fg)]">
        The agent <span className="font-medium text-[var(--fg)]">proposes</span> — this call is
        forwarded to the backend as a pending write. It never changes anything on its own.
      </p>
    </div>
  );
}

// ── Step 2: the approval engine decides ─────────────────────────────────────

export function RuleMatchStage({ outcome }: { outcome: OutcomeId }) {
  const current = outcomeById(outcome);
  const Icon = current.icon;
  return (
    <div className="flex flex-col gap-4">
      <div
        className="hiw-pop rounded-lg border border-[var(--border)] border-l-2 bg-[var(--muted)]/50 p-3"
        style={{ borderLeftColor: `var(--${current.tone})` }}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
            {current.matched ? "Matched rule" : "No match"}
          </span>
          <Badge className="border-[var(--border)] bg-[var(--bg)] font-mono text-[var(--muted-fg)]">
            update_module_data
          </Badge>
          <span
            className="ml-auto inline-flex items-center gap-1 font-mono text-xs font-medium"
            style={{ color: `var(--${current.tone})` }}
          >
            <Icon className="size-3.5" />
            {current.verb}
          </span>
        </div>
        <p
          className={cn(
            "mt-1.5 font-mono text-xs",
            current.matched ? "text-[var(--fg)]" : "italic text-[var(--muted-fg)]",
          )}
        >
          {current.rule}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2" role="presentation">
        {OUTCOMES.map((o) => {
          const on = o.id === outcome;
          const LaneIcon = o.icon;
          return (
            <div
              key={o.id}
              aria-current={on ? "true" : undefined}
              className={cn(
                "flex flex-col items-center gap-1 rounded-lg border px-2 py-3 text-center transition-all",
                on ? "shadow-sm" : "border-[var(--border)] opacity-45",
              )}
              style={on ? toneTint(o.tone) : undefined}
            >
              <LaneIcon className="size-5" style={{ color: `var(--${o.tone})` }} />
              <span
                className="text-[11px] font-medium"
                style={on ? { color: `var(--${o.tone})` } : undefined}
              >
                {o.label}
              </span>
            </div>
          );
        })}
      </div>

      <p className="text-xs leading-relaxed text-[var(--muted-fg)]">{current.blurb}</p>
    </div>
  );
}

// ── Step 3: you review what's pending ───────────────────────────────────────

type ReviewStatus = { tone: Tone; icon: LucideIcon; text: string };

export function ReviewStage({
  outcome,
  approved,
  onApprove,
}: {
  outcome: OutcomeId;
  approved: boolean;
  onApprove: () => void;
}) {
  const [showDetails, setShowDetails] = useState(false);
  const actionable = outcome === "pending" && !approved;
  const queueCount = actionable ? 1 : 0;

  let status: ReviewStatus;
  if (outcome === "auto") {
    status = {
      tone: "success",
      icon: ShieldCheck,
      text: "Auto-approved by a rule — it skipped the queue and applied immediately.",
    };
  } else if (outcome === "deny") {
    status = {
      tone: "danger",
      icon: ShieldX,
      text: "Auto-denied by a rule — logged in Activity, never applied.",
    };
  } else if (approved) {
    status = {
      tone: "success",
      icon: Check,
      text: "Approved — applied to your dashboard. Tip: “Approve + rule” auto-decides writes like this next time.",
    };
  } else {
    status = {
      tone: "warning",
      icon: Clock,
      text: "Waiting for your decision — approve or deny below.",
    };
  }
  const StatusIcon = status.icon;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-xs">
        <span className="font-medium text-[var(--fg)]">Approvals</span>
        {queueCount > 0 ? (
          <Badge tone="solid">{queueCount} pending</Badge>
        ) : (
          <Badge tone="neutral">nothing to review</Badge>
        )}
      </div>

      <Card className={cn("overflow-hidden", !actionable && "opacity-90")}>
        <div className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <AgentBadge agentId="agt_ops-bot" displayName="ops-bot" />
            <Badge tone="neutral">Update data</Badge>
            <span className="truncate text-sm font-medium">System health</span>
            <span className="ml-auto text-[var(--muted-fg)]">just now</span>
          </div>

          <div className="text-xs text-[var(--muted-fg)]">fields: Disk</div>

          <div
            className="flex items-start gap-2 rounded-lg border px-2.5 py-1.5 text-xs"
            style={toneTint(status.tone, { bg: 12, border: 30 })}
          >
            <StatusIcon className="mt-px size-3.5 shrink-0" />
            <span>{status.text}</span>
          </div>

          <button
            type="button"
            onClick={() => setShowDetails((s) => !s)}
            aria-expanded={showDetails}
            className="inline-flex w-fit items-center gap-1 rounded-md text-xs text-[var(--muted-fg)] transition-colors hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            {showDetails ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
            {showDetails ? "Hide details" : "Show details"}
          </button>

          <div className="hiw-collapsible -mt-1" data-open={showDetails}>
            <div>
              <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/40 p-2.5">
                <div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
                  Preview
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className={cn("rounded border px-1.5 py-0.5 font-mono", severityChipClass("success"))}>
                    Disk 64%
                  </span>
                  <ArrowRight className="size-3 text-[var(--muted-fg)]" />
                  <span className={cn("rounded border px-1.5 py-0.5 font-mono", severityChipClass("warning"))}>
                    Disk 81%
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={!actionable} onClick={actionable ? onApprove : undefined}>
              <Check className="size-4" /> Approve
            </Button>
            <Button size="sm" variant="secondary" disabled>
              <ShieldCheck className="size-4" /> Approve + rule
            </Button>
            <Button size="sm" variant="outline" disabled>
              <X className="size-4" /> Deny
            </Button>
            <Button size="sm" variant="outline" disabled>
              <ShieldX className="size-4" /> Deny + rule
            </Button>
          </div>

          <p className="sr-only">
            Illustrative preview of an approval request.{" "}
            {actionable
              ? "Activating Approve advances the walkthrough."
              : "The buttons are non-functional here."}
          </p>
        </div>
      </Card>
    </div>
  );
}

// ── Step 4: your dashboard updates ──────────────────────────────────────────

function KvRow({ k, v, sev }: { k: string; v: string; sev: Severity }) {
  return (
    <div className="contents">
      <dt className="text-[var(--muted-fg)]">{k}</dt>
      <dd
        className={cn(
          "inline-flex w-fit items-center rounded-md border px-2 py-0.5",
          severityChipClass(sev),
        )}
      >
        {v}
      </dd>
    </div>
  );
}

function Sparkline() {
  const pts = [9, 11, 8, 13, 12, 16, 14, 19, 17, 21, 20];
  const max = Math.max(...pts);
  const min = Math.min(...pts);
  const w = 240;
  const h = 56;
  const coords = pts.map((p, i) => {
    const x = (i / (pts.length - 1)) * w;
    const y = h - ((p - min) / (max - min)) * (h - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-14 w-full" preserveAspectRatio="none" aria-hidden>
      <polygon
        points={`0,${h} ${coords.join(" ")} ${w},${h}`}
        fill="color-mix(in srgb, var(--accent) 14%, transparent)"
      />
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MiniModuleCard({
  title,
  type,
  flash = false,
  children,
}: {
  title: string;
  type: string;
  flash?: boolean;
  children: React.ReactNode;
}) {
  // Mirrors ModuleHost: header (title + uppercase type + relative time) and a
  // 900ms accent ring on update.
  return (
    <Card className={cn("flex flex-col transition-shadow", flash && "ring-2 ring-[var(--accent)]/40")}>
      <CardHeader className="flex-row items-center justify-between gap-2 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <CardTitle className="truncate">{title}</CardTitle>
          <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">{type}</span>
        </div>
        <span className="hidden text-xs text-[var(--muted-fg)] sm:inline">just now</span>
      </CardHeader>
      <CardBody>{children}</CardBody>
    </Card>
  );
}

export function DashboardStage({ outcome, applied }: { outcome: OutcomeId; applied: boolean }) {
  const [flash, setFlash] = useState(applied);
  useEffect(() => {
    if (!applied) return;
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 900);
    return () => clearTimeout(t);
  }, [applied]);

  const ghostTone: Tone = outcome === "deny" ? "danger" : "warning";
  const GhostIcon = outcome === "deny" ? XCircle : Clock;

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <MiniModuleCard title="System health" type="key/value" flash={flash}>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
          <KvRow k="CPU" v="32%" sev="success" />
          <KvRow k="Disk" v={applied ? "81%" : "64%"} sev={applied ? "warning" : "success"} />
          <KvRow k="Memory" v="58%" sev="success" />
        </dl>
        {!applied && (
          <div
            className="mt-3 flex items-center gap-2 rounded-lg border border-dashed px-2 py-1.5 text-xs"
            style={{
              borderColor: `color-mix(in srgb, var(--${ghostTone}) 45%, transparent)`,
              color: `var(--${ghostTone})`,
            }}
          >
            <GhostIcon className="size-3.5 shrink-0" />
            <span>
              Proposed: Disk → 81% —{" "}
              {outcome === "deny" ? "denied, never applied" : "unchanged until you approve"}
            </span>
          </div>
        )}
      </MiniModuleCard>

      <MiniModuleCard title="Requests / min" type="timeseries">
        <Sparkline />
      </MiniModuleCard>
    </div>
  );
}
