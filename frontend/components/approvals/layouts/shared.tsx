"use client";

/**
 * Shared visual layer for the Approvals layouts.
 *
 * Locked design decisions (carried over from the design lab):
 *   - Color encodes the ACTION FAMILY (cool palette); green/red are reserved
 *     strictly for the approve/deny affordances.
 *   - Agent = grouping structure, action family = colored rail/icon per row.
 *     Both stay legible at once.
 *
 * Everything here is derived from the real `ApprovalRequest`/`Agent` shapes so
 * the layouts render live data. `ApprovalsView` owns all state/logic and feeds
 * each layout an `ApprovalLayoutProps` bundle.
 */

import {
  AlertTriangle,
  Check,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  UserPlus,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import type { Agent, ApprovalRequest, Module, Page } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime, relativeTime } from "@/lib/time";

// --- Action families -------------------------------------------------------

export type ActionFamily = "create" | "update" | "delete" | "fire" | "register";

export const FAMILY_ORDER: ActionFamily[] = ["create", "update", "delete", "fire", "register"];

export function classifyFamily(actionType: string): ActionFamily {
  if (actionType.startsWith("create")) return "create";
  if (actionType.startsWith("update")) return "update";
  if (actionType.startsWith("delete")) return "delete";
  if (actionType === "fire_action_button") return "fire";
  if (actionType === "register_agent") return "register";
  return "update";
}

/** Human risk tag for the families that carry a side-effect. */
export function riskFor(family: ActionFamily): string | null {
  if (family === "delete") return "destructive";
  if (family === "fire") return "side-effect";
  if (family === "register") return "security";
  return null;
}

export type FamilyStyle = {
  label: string;
  icon: LucideIcon;
  /** Solid fill — used for the left rail and dots. */
  rail: string;
  /** Soft tint — used for chips and card backgrounds. */
  tint: string;
  text: string;
  border: string;
  ring: string;
};

export const FAMILY_STYLES: Record<ActionFamily, FamilyStyle> = {
  create: {
    label: "Create",
    icon: Plus,
    rail: "bg-blue-500",
    tint: "bg-blue-500/10",
    text: "text-blue-700 dark:text-blue-300",
    border: "border-blue-500/30",
    ring: "ring-blue-500/30",
  },
  update: {
    label: "Update",
    icon: Pencil,
    rail: "bg-sky-500",
    tint: "bg-sky-500/10",
    text: "text-sky-700 dark:text-sky-300",
    border: "border-sky-500/30",
    ring: "ring-sky-500/30",
  },
  delete: {
    label: "Delete",
    icon: Trash2,
    rail: "bg-amber-500",
    tint: "bg-amber-500/10",
    text: "text-amber-700 dark:text-amber-300",
    border: "border-amber-500/30",
    ring: "ring-amber-500/30",
  },
  fire: {
    label: "Fire",
    icon: Zap,
    rail: "bg-violet-500",
    tint: "bg-violet-500/10",
    text: "text-violet-700 dark:text-violet-300",
    border: "border-violet-500/30",
    ring: "ring-violet-500/30",
  },
  register: {
    label: "Register",
    icon: UserPlus,
    rail: "bg-zinc-400",
    tint: "bg-zinc-500/10",
    text: "text-zinc-600 dark:text-zinc-300",
    border: "border-zinc-500/30",
    ring: "ring-zinc-500/30",
  },
};

// --- Agent palette (distinct from family hues AND from green/red) ----------

export const AGENT_PALETTE = [
  { avatar: "bg-teal-500/15 text-teal-700 dark:text-teal-300 ring-1 ring-inset ring-teal-500/30", dot: "bg-teal-500" },
  { avatar: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 ring-1 ring-inset ring-indigo-500/30", dot: "bg-indigo-500" },
  { avatar: "bg-orange-500/15 text-orange-700 dark:text-orange-300 ring-1 ring-inset ring-orange-500/30", dot: "bg-orange-500" },
  { avatar: "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300 ring-1 ring-inset ring-fuchsia-500/30", dot: "bg-fuchsia-500" },
  { avatar: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 ring-1 ring-inset ring-cyan-500/30", dot: "bg-cyan-500" },
  { avatar: "bg-slate-500/15 text-slate-700 dark:text-slate-300 ring-1 ring-inset ring-slate-500/30", dot: "bg-slate-500" },
];

/** Stable palette slot for an agent — hashed from its id (or name fallback). */
export function agentPaletteIndex(key: string | null | undefined): number {
  const s = key ?? "";
  let h = 0;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % AGENT_PALETTE.length;
}

export function initials(name: string): string {
  const parts = name.replace(/[^a-zA-Z0-9 -]/g, "").split(/[ \-_]/).filter(Boolean);
  const [first, second] = parts;
  if (!first) return "?";
  if (!second) return first.slice(0, 2).toUpperCase();
  return (first.charAt(0) + second.charAt(0)).toUpperCase();
}

// --- Request → human strings (shared by ApprovalCard + every layout) --------

export function actionTypeLabel(action: string): string {
  switch (action) {
    case "create_module":
      return "Create module";
    case "update_module_data":
      return "Update data";
    case "update_module_config":
      return "Update config";
    case "update_module_meta":
      return "Update meta";
    case "update_module_capability":
      return "Change capability";
    case "delete_module":
      return "Delete module";
    case "create_page":
      return "Create page";
    case "delete_page":
      return "Delete page";
    case "fire_action_button":
      return "Fire action";
    case "register_file":
      return "Register file";
    case "register_agent":
      return "Register agent";
    default:
      return action;
  }
}

export function describeTarget(
  req: ApprovalRequest,
  modulesById: Map<string, Module>,
  pagesById: Map<string, Page>,
): string {
  const payload = req.proposed_payload ?? {};
  if (req.action_type === "register_agent") {
    const name = (payload.display_name as string | undefined) ?? "new agent";
    return `Register ${name}`;
  }
  if (req.action_type === "create_module") {
    const moduleType = (payload.type as string | undefined) ?? "module";
    const pageId = payload.page_id as string | undefined;
    const page = pageId ? pagesById.get(pageId) : undefined;
    return `Create ${moduleType} on ${page?.name ?? pageId ?? "(page)"}`;
  }
  if (req.action_type === "create_page") {
    const name = (payload.name as string | undefined) ?? (payload.slug as string | undefined);
    return `Create page ${name ?? ""}`.trim();
  }
  if (req.target_kind === "module" && req.target_id) {
    const targetModule = modulesById.get(req.target_id);
    return targetModule
      ? targetModule.title ?? `${targetModule.type} (${targetModule.id.slice(-6)})`
      : req.target_id;
  }
  if (req.target_kind === "page" && req.target_id) {
    const page = pagesById.get(req.target_id);
    return page?.name ?? req.target_id;
  }
  if (req.target_kind === "action_target" && req.target_id) {
    return `action: ${req.target_id}`;
  }
  return "—";
}

export function summarize(req: ApprovalRequest): string {
  const payload = req.proposed_payload ?? {};
  if (req.action_type === "update_module_data" || req.action_type === "update_module_config") {
    const patch = (payload.patch as Record<string, unknown> | undefined) ?? {};
    const changedFields =
      (patch.data as Record<string, unknown> | undefined) ??
      (patch.config as Record<string, unknown> | undefined) ??
      {};
    const keys = Object.keys(changedFields);
    if (keys.length === 0) return "no changed keys";
    const firstKeys = keys.slice(0, 3).join(", ");
    return keys.length > 3 ? `${firstKeys}, +${keys.length - 3} more` : firstKeys;
  }
  if (req.action_type === "create_module") {
    const title = payload.title as string | undefined;
    return title ? `“${title}”` : "(no title)";
  }
  if (req.action_type === "fire_action_button") {
    return "Trigger action";
  }
  if (req.action_type === "register_agent") {
    const hint = payload.client_hint as string | undefined;
    return hint ? `from ${hint}` : "";
  }
  return "";
}

// --- View model + layout contract ------------------------------------------

/** Everything a layout needs to render one request, pre-derived once. */
export type ApprovalRowVM = {
  request: ApprovalRequest;
  family: ActionFamily;
  agent: Agent | undefined;
  /** Display name for the actor (registered agent or prospective new agent). */
  agentLabel: string;
  target: string;
  summary: string;
  /** "destructive" | "side-effect" | "security" | null */
  risk: string | null;
  destructive: boolean;
  /** Relative age string, e.g. "2m ago". */
  age: string;
};

export function buildRows(
  requests: ApprovalRequest[],
  agentsById: Map<string, Agent>,
  modulesById: Map<string, Module>,
  pagesById: Map<string, Page>,
): ApprovalRowVM[] {
  return requests.map((request) => {
    const family = classifyFamily(request.action_type);
    const agent = request.agent_id ? agentsById.get(request.agent_id) : undefined;
    const registrationName =
      request.action_type === "register_agent"
        ? (request.proposed_payload?.display_name as string | undefined)
        : undefined;
    const agentLabel =
      agent?.display_name ?? registrationName ?? (request.agent_id ?? "New agent");
    const risk = riskFor(family);
    return {
      request,
      family,
      agent,
      agentLabel,
      target: describeTarget(request, modulesById, pagesById),
      summary: summarize(request),
      risk,
      destructive: family === "delete" || family === "fire" || family === "register",
      age: relativeTime(request.created_at),
    };
  });
}

/** Props every layout receives from `ApprovalsView`. */
export type ApprovalLayoutProps = {
  rows: ApprovalRowVM[];
  agents: Agent[];
  selectedIds: Set<string>;
  busyIds: Set<string>;
  /** A bulk decision is in flight — group/bulk actions should lock out. */
  bulkBusy?: boolean;
  onToggleSelect: (id: string) => void;
  onApprove: (id: string, withRule: boolean) => void;
  onDeny: (id: string, withRule: boolean) => void;
  onApproveMany: (ids: string[]) => void;
  onDenyMany: (ids: string[]) => void;
  /** Prefetch the preview detail for a request (on hover/expand/select). */
  onWantDetail: (id: string) => void;
  /** Render a fully-wired `ApprovalCard` for the detail/expanded view. */
  renderCard: (request: ApprovalRequest, opts?: { defaultExpanded?: boolean }) => ReactNode;
};

// --- Grouping --------------------------------------------------------------

export type ApprovalAgentGroup = {
  key: string;
  label: string;
  agentId: string | null;
  kind: "agent" | "new";
  rows: ApprovalRowVM[];
};

/** Group rows by their actor, preserving first-seen order. */
export function groupRowsByAgent(rows: ApprovalRowVM[]): ApprovalAgentGroup[] {
  const order: ApprovalAgentGroup[] = [];
  const byKey = new Map<string, ApprovalAgentGroup>();
  for (const vm of rows) {
    const key = vm.request.agent_id ?? "__new__";
    let group = byKey.get(key);
    if (!group) {
      group = {
        key,
        label: vm.request.agent_id ? vm.agentLabel : "New agents",
        agentId: vm.request.agent_id,
        kind: vm.request.agent_id ? "agent" : "new",
        rows: [],
      };
      byKey.set(key, group);
      order.push(group);
    }
    group.rows.push(vm);
  }
  return order;
}

export function familyCounts(rows: ApprovalRowVM[]): Record<ActionFamily, number> {
  const counts: Record<ActionFamily, number> = {
    create: 0,
    update: 0,
    delete: 0,
    fire: 0,
    register: 0,
  };
  for (const r of rows) counts[r.family] += 1;
  return counts;
}

// --- Atoms -----------------------------------------------------------------

export function AgentAvatar({
  agentId,
  name,
  size = "md",
}: {
  agentId: string | null | undefined;
  name: string;
  size?: "sm" | "md" | "lg";
}) {
  const s = AGENT_PALETTE[agentPaletteIndex(agentId ?? name)] ?? AGENT_PALETTE[0]!;
  const dim =
    size === "lg"
      ? "size-9 text-sm"
      : size === "sm"
        ? "size-5 text-[9px]"
        : "size-7 text-[11px]";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        dim,
        s.avatar,
      )}
      title={name}
    >
      {initials(name)}
    </span>
  );
}

export function FamilyIcon({ family, className }: { family: ActionFamily; className?: string }) {
  const Icon = FAMILY_STYLES[family].icon;
  return <Icon className={cn("size-3.5", className)} />;
}

/**
 * Bulk-select checkbox. Supports the indeterminate ("some of this group") state
 * that only the DOM node can express, and never lets its click reach the row
 * underneath it.
 */
export function SelectCheckbox({
  checked,
  indeterminate,
  label,
  onChange,
  className,
}: {
  checked: boolean;
  indeterminate?: boolean;
  label: string;
  onChange: () => void;
  className?: string;
}) {
  const ref = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = Boolean(indeterminate) && !checked;
  }, [indeterminate, checked]);
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={label}
      title={label}
      checked={checked}
      onChange={onChange}
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "size-4 shrink-0 cursor-pointer accent-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
        className,
      )}
    />
  );
}

/** What's inside a group, at a glance — one counted dot per action family. */
export function FamilyDots({
  rows,
  className,
}: {
  rows: ApprovalRowVM[];
  className?: string;
}) {
  const counts = familyCounts(rows);
  const present = FAMILY_ORDER.filter((f) => counts[f] > 0);
  if (present.length === 0) return null;
  return (
    <span
      className={cn("inline-flex items-center gap-1.5", className)}
      title={present.map((f) => `${counts[f]} ${FAMILY_STYLES[f].label.toLowerCase()}`).join(" · ")}
    >
      {present.map((f) => (
        <span
          key={f}
          className="inline-flex items-center gap-1 text-[10px] tabular-nums text-[var(--muted-fg)]"
        >
          <span className={cn("size-1.5 rounded-full", FAMILY_STYLES[f].rail)} />
          {counts[f]}
        </span>
      ))}
    </span>
  );
}

/** Keycap chip for the inbox shortcut legend. */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border border-[var(--border-strong)] bg-[var(--muted)] px-1 font-mono text-[10px] font-medium text-[var(--fg)]">
      {children}
    </kbd>
  );
}

export function RiskBadge({ label }: { label: string | null }) {
  if (!label) return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[var(--warning)]/25 bg-[var(--warning-soft)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--warning)]">
      <AlertTriangle className="size-3" /> {label}
    </span>
  );
}

/** Compact approve/deny icon pair. */
export function MiniDecide({
  onApprove,
  onDeny,
  disabled,
  className,
}: {
  onApprove: () => void;
  onDeny: () => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1", className)}>
      <button
        type="button"
        title="Approve (a)"
        aria-label="Approve"
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation();
          onApprove();
        }}
        className="inline-flex size-7 items-center justify-center rounded-lg text-[var(--success)] transition-colors hover:bg-[var(--success-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:pointer-events-none disabled:opacity-40"
      >
        <Check className="size-4" />
      </button>
      <button
        type="button"
        title="Deny (d)"
        aria-label="Deny"
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation();
          onDeny();
        }}
        className="inline-flex size-7 items-center justify-center rounded-lg text-[var(--danger)] transition-colors hover:bg-[var(--danger-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:pointer-events-none disabled:opacity-40"
      >
        <X className="size-4" />
      </button>
    </span>
  );
}

/**
 * A single dense request row with a colored family rail.
 *
 * The row carries a roving tabindex: the layout's keyboard cursor owns
 * `tabIndex={0}` so Tab lands on the row you were last on rather than walking
 * every row in the queue. It stays a plain focusable div — the approve/deny
 * buttons and the select checkbox live inside it, which `role="button"` would
 * forbid — so the caller owns the surrounding list semantics.
 */
export function CompactRow({
  vm,
  active,
  cursor,
  expanded,
  busy,
  showAgent,
  selected,
  onToggleSelect,
  onClick,
  onApprove,
  onDeny,
  elementRef,
  tabIndex,
}: {
  vm: ApprovalRowVM;
  /** Row is the current selection in a master/detail pane. */
  active?: boolean;
  /** Row holds the keyboard cursor (shows a persistent focus ring). */
  cursor?: boolean;
  /** Row's detail card is open below it. */
  expanded?: boolean;
  /** A decision for this row is in flight. */
  busy?: boolean;
  showAgent?: boolean;
  selected?: boolean;
  /** Omit to hide the bulk-select checkbox entirely. */
  onToggleSelect?: () => void;
  onClick?: () => void;
  onApprove: () => void;
  onDeny: () => void;
  elementRef?: (el: HTMLDivElement | null) => void;
  tabIndex?: number;
}) {
  const st = FAMILY_STYLES[vm.family];
  const highlighted = expanded || active;
  return (
    <div
      ref={elementRef}
      tabIndex={onClick ? (tabIndex ?? -1) : undefined}
      aria-expanded={onClick ? Boolean(expanded) : undefined}
      aria-current={cursor ? true : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (!onClick) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "group flex scroll-mt-24 items-center gap-2 rounded-lg py-1.5 pl-2 pr-1.5 text-sm outline-none transition-colors",
        onClick && "cursor-pointer",
        highlighted ? "bg-[var(--accent-soft)]" : "hover:bg-[var(--muted)]/60",
        cursor && "ring-2 ring-inset ring-[var(--accent)]",
        busy && "opacity-60",
      )}
    >
      <span aria-hidden="true" className={cn("h-7 w-1 shrink-0 rounded-full", st.rail)} />
      {onToggleSelect && (
        <SelectCheckbox
          checked={Boolean(selected)}
          label="Select for bulk action"
          onChange={onToggleSelect}
        />
      )}
      {busy ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin text-[var(--muted-fg)]" />
      ) : (
        <FamilyIcon family={vm.family} className={cn("shrink-0", st.text)} />
      )}
      {showAgent && <AgentAvatar agentId={vm.request.agent_id} name={vm.agentLabel} size="sm" />}
      <span className="shrink-0 font-medium">{actionTypeLabel(vm.request.action_type)}</span>
      <span
        className="min-w-0 flex-1 truncate font-mono text-xs text-[var(--muted-fg)]"
        title={vm.target}
      >
        {vm.target}
      </span>
      {vm.summary && (
        <span
          className="hidden max-w-[22ch] shrink truncate text-xs text-[var(--muted-fg)]/80 lg:inline"
          title={vm.summary}
        >
          {vm.summary}
        </span>
      )}
      <RiskBadge label={vm.risk} />
      <span
        className="shrink-0 whitespace-nowrap text-xs tabular-nums text-[var(--muted-fg)]"
        title={formatDateTime(vm.request.created_at)}
      >
        {vm.age}
      </span>
      <MiniDecide
        disabled={busy}
        className="opacity-70 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
        onApprove={onApprove}
        onDeny={onDeny}
      />
    </div>
  );
}
