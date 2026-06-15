import {
  Bot,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  LayoutDashboard,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { CSSProperties } from "react";

/**
 * Shared data + helpers for the interactive "core flow" simulator on the
 * How it Works page. Kept framework-free (no JSX) so both the simulator shell
 * (CoreFlowSimulator) and the per-step demo panels (SimulatorStages) can import
 * it without a circular dependency.
 *
 * The simulator teaches the one idea the product exists for: the SAME proposed
 * agent write branches three ways depending on the matching rule. So there are
 * two independent axes —
 *   • STAGES   — the four steps of the pipeline (a WAI-ARIA tablist), and
 *   • OUTCOMES — which branch the engine takes (a radiogroup the user scrubs).
 */

export type Tone = "success" | "warning" | "danger" | "accent";

/** A token-derived tint, theme-aware (the CSS var flips in dark mode). */
export function toneTint(
  tone: Tone,
  { bg = 14, border = 38 }: { bg?: number; border?: number } = {},
): CSSProperties {
  const v = `var(--${tone})`;
  return {
    backgroundColor: `color-mix(in srgb, ${v} ${bg}%, transparent)`,
    borderColor: `color-mix(in srgb, ${v} ${border}%, transparent)`,
    color: v,
  };
}

export type OutcomeId = "auto" | "pending" | "deny";

export type Outcome = {
  id: OutcomeId;
  label: string;
  tone: Tone;
  icon: LucideIcon;
  /** The rule condition shown in the "matched rule" readout for this branch. */
  rule: string;
  /** Whether a rule matched, or the engine fell through to prompting. */
  matched: boolean;
  /** The engine's verb, mirroring the audit log outcome vocabulary. */
  verb: string;
  /** One-line plain-English consequence, used in captions + the rule readout. */
  blurb: string;
};

export const OUTCOMES = [
  {
    id: "auto",
    label: "Auto-approve",
    tone: "success",
    icon: CheckCircle2,
    rule: "agent = ops-bot AND module.type = key_value",
    matched: true,
    verb: "auto_approve",
    blurb: "A rule matched, so the write applied to your dashboard immediately — no prompt.",
  },
  {
    id: "pending",
    label: "Pending",
    tone: "warning",
    icon: Clock,
    rule: "No rule matched → prompt admin",
    matched: false,
    verb: "prompt",
    blurb: "Nothing matched, so it waits in Approvals (7-day TTL) for your decision.",
  },
  {
    id: "deny",
    label: "Deny",
    tone: "danger",
    icon: XCircle,
    rule: "payload.severity = warning → deny",
    matched: true,
    verb: "deny",
    blurb: "A rule denied it — logged in Activity, but never applied.",
  },
] as const;

export function outcomeById(id: OutcomeId): Outcome {
  return OUTCOMES.find((o) => o.id === id) ?? OUTCOMES[0];
}

export type Stage = {
  id: "propose" | "decide" | "review" | "apply";
  /** Short label shown under the rail node. */
  rail: string;
  /** Full heading shown in the demo panel. */
  title: string;
  explain: string;
  icon: LucideIcon;
};

export const STAGES = [
  {
    id: "propose",
    rail: "Agent proposes",
    title: "An agent proposes a change",
    explain:
      "An MCP agent calls a write tool like update_module_data. Nothing changes yet — the call is forwarded to the backend as a proposed write. Agents never touch your dashboard directly.",
    icon: Bot,
  },
  {
    id: "decide",
    rail: "Engine decides",
    title: "The approval engine decides",
    explain:
      "The engine matches your rules — most specific first, then by priority. The first match wins; if nothing matches it defaults to prompting you. The same proposal can auto-approve, queue, or be denied depending on the matching rule.",
    icon: ShieldCheck,
  },
  {
    id: "review",
    rail: "You review",
    title: "You review what's pending",
    explain:
      "Anything not auto-decided lands in Approvals with a 7-day TTL. You get a preview, then approve or deny — optionally saving a rule so similar writes decide themselves next time.",
    icon: ClipboardCheck,
  },
  {
    id: "apply",
    rail: "Dashboard updates",
    title: "Your dashboard updates",
    explain:
      "An approved write applies immediately. A denied or expired one is logged in Activity but never touches your dashboard.",
    icon: LayoutDashboard,
  },
] as const;
