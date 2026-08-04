"use client";

import { Check, ChevronDown, ChevronUp, ShieldCheck, SlidersHorizontal, X } from "lucide-react";
import { useRef, useState } from "react";

import { AgentBadge } from "@/components/agents/AgentBadge";
import { ApprovalActionPreview } from "@/components/approvals/ApprovalActionPreview";
import { ApprovalFilePreview } from "@/components/approvals/ApprovalFilePreview";
import { ApprovalPagePreview } from "@/components/approvals/ApprovalPagePreview";
import { ApprovalRegistrationPreview } from "@/components/approvals/ApprovalRegistrationPreview";
import {
  FAMILY_STYLES,
  RiskBadge,
  actionTypeLabel,
  classifyFamily,
  describeTarget,
  riskFor,
  summarize,
} from "@/components/approvals/layouts/shared";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { ActionPreview, Agent, ApprovalRequest, DashboardPreview, FilePreview, IframeAllowlistEntry, Module, Page, RegistrationPreview } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativeTime, formatDateTime } from "@/lib/time";

// Phase 6: mobile swipe gestures.
// Swipe-right (>= 50% card width OR fast flick) → approve.
// Swipe-left  → deny. Buttons remain visible as the primary affordance for
// pointer users; the gesture is an addition, not a replacement.
const SWIPE_TRIGGER_FRACTION = 0.5;
const SWIPE_VELOCITY_PX_PER_MS = 0.6;

type ApprovalCardProps = {
  request: ApprovalRequest;
  diffPreview?: Record<string, unknown> | null;
  dashboardPreview?: DashboardPreview | null;
  actionPreview?: ActionPreview | null;
  filePreview?: FilePreview | null;
  registrationPreview?: RegistrationPreview | null;
  detailLoading?: boolean;
  detailFetched?: boolean;
  /** Start with the preview section open (used by the compact layouts). */
  defaultExpanded?: boolean;
  iframeAllowlist?: IframeAllowlistEntry[];
  selected: boolean;
  onToggleSelect: () => void;
  onExpand?: () => void;
  agentsById: Map<string, Agent>;
  modulesById: Map<string, Module>;
  pagesById: Map<string, Page>;
  busy?: boolean;
  onApprove: (withRule: boolean) => void;
  onDeny: () => void;
  onAdjustRules: () => void;
  /**
   * Long-press handler used on mobile to enter multi-select mode without
   * needing a visible checkbox tap.
   */
  onLongPress?: () => void;
};

export function ApprovalCard({
  request,
  diffPreview,
  dashboardPreview,
  actionPreview,
  filePreview,
  registrationPreview,
  detailLoading,
  detailFetched,
  defaultExpanded,
  iframeAllowlist,
  selected,
  onToggleSelect,
  onExpand,
  agentsById,
  modulesById,
  pagesById,
  busy,
  onApprove,
  onDeny,
  onAdjustRules,
  onLongPress,
}: ApprovalCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);
  const [showTechnical, setShowTechnical] = useState(false);
  const [swipeX, setSwipeX] = useState(0);
  const swipeStartRef = useRef<{ x: number; y: number; t: number; width: number } | null>(
    null,
  );
  const containerRef = useRef<HTMLDivElement | null>(null);
  const family = classifyFamily(request.action_type);
  const familyStyle = FAMILY_STYLES[family];
  const risk = riskFor(family);
  const agent = request.agent_id ? agentsById.get(request.agent_id) : undefined;
  const registrationName =
    request.action_type === "register_agent"
      ? ((request.proposed_payload?.display_name as string | undefined) ??
        registrationPreview?.requested_name ??
        "New agent")
      : undefined;
  const target = describeTarget(request, modulesById, pagesById);

  // Long-press for mobile multi-select.
  let pressTimer: ReturnType<typeof setTimeout> | null = null;
  function startPress() {
    if (!onLongPress) return;
    pressTimer = setTimeout(() => {
      onLongPress();
    }, 450);
  }
  function endPress() {
    if (pressTimer) clearTimeout(pressTimer);
    pressTimer = null;
  }

  // ---- Phase 6 swipe gestures ----
  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    // Pointer events with pointerType==="mouse" are ignored — swiping by
    // mouse is not a desired interaction; ditto for pen.
    if (e.pointerType !== "touch") return;
    const node = containerRef.current;
    if (!node) return;
    swipeStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      t: performance.now(),
      width: node.getBoundingClientRect().width,
    };
  }
  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const s = swipeStartRef.current;
    if (!s) return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    // Only treat as swipe if horizontal dominance is clear.
    if (Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      // Clamp so the card doesn't fly off the screen.
      setSwipeX(Math.max(-s.width, Math.min(s.width, dx)));
    }
  }
  function onPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    const s = swipeStartRef.current;
    swipeStartRef.current = null;
    if (!s) return;
    const dx = e.clientX - s.x;
    const dt = performance.now() - s.t;
    const velocity = dt > 0 ? Math.abs(dx) / dt : 0;
    const threshold = s.width * SWIPE_TRIGGER_FRACTION;
    const overThreshold = Math.abs(dx) >= threshold;
    const fastFlick = velocity >= SWIPE_VELOCITY_PX_PER_MS;
    if (overThreshold || fastFlick) {
      if (dx > 0) {
        onApprove(false);
      } else {
        onDeny();
      }
    }
    // Reset visual position whether or not we triggered.
    setSwipeX(0);
  }

  // Background severity reflects swipe direction; subtle until threshold.
  const swipeBgColor =
    swipeX > 0
      ? "var(--success)"
      : swipeX < 0
        ? "var(--danger)"
        : "transparent";
  const swipeIcon = swipeX > 0 ? <Check className="size-5" /> : swipeX < 0 ? <X className="size-5" /> : null;

  return (
    <Card
      className={cn(
        "relative overflow-hidden transition-all",
        selected && "border-[var(--accent-border)] ring-2 ring-[var(--accent)]",
      )}
    >
      {/* Family-colored rail (action type at a glance). */}
      <span
        aria-hidden="true"
        className={cn("absolute inset-y-0 left-0 z-10 w-1", familyStyle.rail)}
      />
      {/* Reveal layer (gesture only). */}
      {swipeX !== 0 && (
        <div
          aria-hidden="true"
          className={cn(
            "absolute inset-0 flex items-center px-6 text-white",
            swipeX > 0 ? "justify-start" : "justify-end",
          )}
          style={{ background: swipeBgColor, opacity: Math.min(1, Math.abs(swipeX) / 120) }}
        >
          {swipeIcon}
        </div>
      )}
      <div
        ref={containerRef}
        className="relative flex items-start gap-3 p-4 pl-5 bg-[var(--card)] touch-pan-y"
        style={{
          transform: `translateX(${swipeX}px)`,
          transition: swipeStartRef.current ? "none" : "transform 0.18s ease-out",
        }}
        onTouchStart={startPress}
        onTouchEnd={endPress}
        onTouchCancel={endPress}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          swipeStartRef.current = null;
          setSwipeX(0);
        }}
      >
        <input
          type="checkbox"
          aria-label="Select for bulk action"
          checked={selected}
          onChange={onToggleSelect}
          className="mt-1 size-4 shrink-0 accent-[var(--accent)]"
        />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <AgentBadge
              agentId={request.agent_id}
              displayName={
                registrationName ?? agent?.display_name ?? (request.agent_id ? undefined : "New agent")
              }
            />
            <Badge className={cn(familyStyle.tint, familyStyle.text, familyStyle.border)}>
              {actionTypeLabel(request.action_type)}
            </Badge>
            <RiskBadge label={risk} />
            <span className="truncate font-medium text-sm" title={target}>
              {target}
            </span>
            <span
              className="ml-auto text-[var(--muted-fg)]"
              title={formatDateTime(request.created_at)}
            >
              {relativeTime(request.created_at)}
            </span>
          </div>

          <div className="mt-1 text-xs text-[var(--muted-fg)] truncate">
            {summarize(request)}
          </div>

          <button
            type="button"
            className="mt-2 inline-flex items-center gap-1 rounded-lg text-xs text-[var(--muted-fg)] transition-colors hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            onClick={() => {
              setExpanded((e) => {
                const next = !e;
                if (next) onExpand?.();
                return next;
              });
            }}
          >
            {expanded ? (
              <>
                <ChevronUp className="size-3" /> Hide details
              </>
            ) : (
              <>
                <ChevronDown className="size-3" /> Show details
              </>
            )}
          </button>

          {expanded && (
            <div className="mt-2 space-y-2">
              {detailLoading && (
                <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/30 p-4 text-xs text-[var(--muted-fg)] animate-pulse">
                  Loading preview…
                </div>
              )}
              {!detailLoading && dashboardPreview && (
                <ApprovalPagePreview
                  preview={dashboardPreview}
                  iframeAllowlist={iframeAllowlist}
                />
              )}
              {!detailLoading && actionPreview && (
                <ApprovalActionPreview preview={actionPreview} />
              )}
              {!detailLoading && filePreview && (
                <ApprovalFilePreview preview={filePreview} />
              )}
              {!detailLoading && registrationPreview && (
                <ApprovalRegistrationPreview preview={registrationPreview} />
              )}
              {!detailLoading &&
                !dashboardPreview &&
                !actionPreview &&
                !filePreview &&
                !registrationPreview &&
                detailFetched && (
                  <p className="text-xs text-[var(--muted-fg)]">
                    No visual preview for this action type.
                  </p>
                )}

              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-lg text-xs text-[var(--muted-fg)] transition-colors hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                onClick={() => setShowTechnical((s) => !s)}
              >
                {showTechnical ? (
                  <>
                    <ChevronUp className="size-3" /> Hide technical details
                  </>
                ) : (
                  <>
                    <ChevronDown className="size-3" /> Show technical details
                  </>
                )}
              </button>

              {showTechnical && (
                <div className="space-y-2">
                  {diffPreview && Object.keys(diffPreview).length > 0 && (
                    <div>
                      <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
                        Diff
                      </div>
                      <pre className="mt-1 max-h-64 overflow-auto rounded-lg border border-[var(--border)] bg-[var(--muted)] p-3 font-mono text-[11px] leading-snug">
                        {JSON.stringify(diffPreview, null, 2)}
                      </pre>
                    </div>
                  )}
                  <div>
                    <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
                      Proposed payload
                    </div>
                    <pre className="mt-1 max-h-96 overflow-auto rounded-lg border border-[var(--border)] bg-[var(--muted)] p-3 font-mono text-[11px] leading-snug">
                      {JSON.stringify(request.proposed_payload, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" disabled={busy} onClick={() => onApprove(false)}>
              <Check className="size-4" /> Approve
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => onApprove(true)}
            >
              <ShieldCheck className="size-4" /> Approve + Auto-Approve Future Matches
            </Button>
            <Button
              size="sm"
              variant="secondary"
              className="text-[var(--danger)] hover:border-[var(--danger)]/25 hover:bg-[var(--danger-soft)]"
              disabled={busy}
              onClick={onDeny}
            >
              <X className="size-4" /> Deny
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={onAdjustRules}
            >
              <SlidersHorizontal className="size-4" /> Adjust Rules
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
