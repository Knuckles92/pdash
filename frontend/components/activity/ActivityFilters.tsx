"use client";

import { useId } from "react";

import { ACTION_GROUPS, OUTCOMES } from "@/components/activity/activityMeta";
import { Input } from "@/components/ui/Input";
import {
  type ActionTarget,
  type Agent,
  type Module,
  type Page,
} from "@/lib/api";
import { cn } from "@/lib/cn";

export type TimePreset = "" | "24h" | "7d" | "30d";

export const TIME_PRESETS: Array<{ value: TimePreset; label: string; ms: number }> = [
  { value: "", label: "All time", ms: 0 },
  { value: "24h", label: "24h", ms: 24 * 3_600_000 },
  { value: "7d", label: "7d", ms: 7 * 24 * 3_600_000 },
  { value: "30d", label: "30d", ms: 30 * 24 * 3_600_000 },
];

export type ActivityFilters = {
  outcomes: Set<string>;
  kinds: Set<string>;
  actor: string;
  targetKind: string;
  targetId: string;
  preset: TimePreset;
  after: string;
  before: string;
};

export const EMPTY_ACTIVITY_FILTERS: ActivityFilters = {
  outcomes: new Set(),
  kinds: new Set(),
  actor: "",
  targetKind: "",
  targetId: "",
  preset: "",
  after: "",
  before: "",
};

export function hasActiveFilters(f: ActivityFilters): boolean {
  return (
    f.outcomes.size > 0 ||
    f.kinds.size > 0 ||
    !!f.actor ||
    !!f.targetKind ||
    !!f.targetId ||
    !!f.preset ||
    !!f.after ||
    !!f.before
  );
}

const SELECT_CLASS =
  "h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 text-sm shadow-[var(--shadow-xs)] transition-[border-color,box-shadow] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]";

type ActivityFiltersPanelProps = {
  filters: ActivityFilters;
  onChange: (next: ActivityFilters) => void;
  agents: Agent[];
  modules: Module[];
  pages: Page[];
  actionTargets: ActionTarget[];
  pagesById: Map<string, Page>;
};

/**
 * The always-on filter controls for the activity feed. Layout-agnostic stack
 * of sections; ActivityView mounts it as a sticky rail on desktop and inside
 * a collapsible card on mobile.
 */
export function ActivityFiltersPanel({
  filters,
  onChange,
  agents,
  modules,
  pages,
  actionTargets,
  pagesById,
}: ActivityFiltersPanelProps) {
  const patch = (p: Partial<ActivityFilters>) => onChange({ ...filters, ...p });

  const toggleOutcome = (value: string) => {
    const next = new Set(filters.outcomes);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    patch({ outcomes: next });
  };

  const toggleKind = (kind: string) => {
    const next = new Set(filters.kinds);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    patch({ kinds: next });
  };

  const toggleGroup = (kinds: string[]) => {
    const next = new Set(filters.kinds);
    const allSelected = kinds.every((k) => next.has(k));
    for (const k of kinds) {
      if (allSelected) next.delete(k);
      else next.add(k);
    }
    patch({ kinds: next });
  };

  const anyKindPartial = ACTION_GROUPS.some((g) => {
    const selected = g.kinds.filter((k) => filters.kinds.has(k)).length;
    return selected > 0 && selected < g.kinds.length;
  });

  return (
    <div className="flex flex-col gap-5">
      <FilterSection
        label="Outcome"
        active={filters.outcomes.size > 0}
        onReset={() => patch({ outcomes: new Set() })}
      >
        <div className="flex flex-col gap-0.5">
          {OUTCOMES.map((o) => {
            const selected = filters.outcomes.has(o.value);
            return (
              <button
                key={o.value}
                type="button"
                aria-pressed={selected}
                onClick={() => toggleOutcome(o.value)}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                  selected
                    ? "bg-[var(--accent-soft)] font-medium text-[var(--fg)]"
                    : "text-[var(--muted-fg)] hover:bg-[var(--muted)]/60 hover:text-[var(--fg)]",
                )}
              >
                <span className={cn("size-2 shrink-0 rounded-full", o.dotClass)} />
                {o.label}
              </button>
            );
          })}
        </div>
      </FilterSection>

      <FilterSection
        label="Actor"
        active={!!filters.actor}
        onReset={() => patch({ actor: "" })}
      >
        <select
          className={SELECT_CLASS}
          value={filters.actor}
          onChange={(e) => patch({ actor: e.target.value })}
        >
          <option value="">Anyone</option>
          <option value="admin">Admin (you)</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name}
            </option>
          ))}
        </select>
      </FilterSection>

      <FilterSection
        label="Action"
        active={filters.kinds.size > 0}
        onReset={() => patch({ kinds: new Set() })}
      >
        <div className="flex flex-wrap gap-1.5">
          {ACTION_GROUPS.map((g) => {
            const selected = g.kinds.filter((k) => filters.kinds.has(k)).length;
            const all = selected === g.kinds.length;
            const partial = selected > 0 && !all;
            return (
              <FilterChip
                key={g.key}
                selected={all}
                partial={partial}
                onClick={() => toggleGroup(g.kinds)}
              >
                {g.label}
              </FilterChip>
            );
          })}
        </div>
        <details className="group mt-2" open={anyKindPartial || undefined}>
          <summary className="cursor-pointer select-none text-xs text-[var(--muted-fg)] transition-colors hover:text-[var(--fg)]">
            Specific actions
          </summary>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ACTION_GROUPS.flatMap((g) => g.kinds).map((k) => (
              <FilterChip
                key={k}
                selected={filters.kinds.has(k)}
                onClick={() => toggleKind(k)}
                mono
              >
                {k}
              </FilterChip>
            ))}
          </div>
        </details>
      </FilterSection>

      <FilterSection
        label="Time"
        active={!!filters.preset || !!filters.after || !!filters.before}
        onReset={() => patch({ preset: "", after: "", before: "" })}
      >
        <div className="grid grid-cols-4 overflow-hidden rounded-lg border border-[var(--border)]">
          {TIME_PRESETS.map((p, i) => {
            const selected = filters.preset === p.value && !filters.after && !filters.before;
            return (
              <button
                key={p.value || "all"}
                type="button"
                aria-pressed={selected}
                onClick={() => patch({ preset: p.value, after: "", before: "" })}
                className={cn(
                  "px-1 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]",
                  i > 0 && "border-l border-[var(--border)]",
                  selected
                    ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                    : "text-[var(--muted-fg)] hover:bg-[var(--muted)]/60 hover:text-[var(--fg)]",
                )}
              >
                {p.label}
              </button>
            );
          })}
        </div>
        <details className="mt-2" open={(!!filters.after || !!filters.before) || undefined}>
          <summary className="cursor-pointer select-none text-xs text-[var(--muted-fg)] transition-colors hover:text-[var(--fg)]">
            Custom range
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            <label className="flex flex-col gap-1 text-xs text-[var(--muted-fg)]">
              After
              <input
                type="datetime-local"
                className={SELECT_CLASS}
                value={filters.after}
                onChange={(e) => patch({ after: e.target.value, preset: "" })}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-[var(--muted-fg)]">
              Before
              <input
                type="datetime-local"
                className={SELECT_CLASS}
                value={filters.before}
                onChange={(e) => patch({ before: e.target.value, preset: "" })}
              />
            </label>
          </div>
        </details>
      </FilterSection>

      <FilterSection
        label="Target"
        active={!!filters.targetKind || !!filters.targetId}
        onReset={() => patch({ targetKind: "", targetId: "" })}
      >
        <div className="flex flex-col gap-2">
          <select
            className={SELECT_CLASS}
            value={filters.targetKind}
            onChange={(e) => patch({ targetKind: e.target.value, targetId: "" })}
          >
            <option value="">Any target</option>
            <option value="module">Module</option>
            <option value="page">Page</option>
            <option value="action_target">Action target</option>
            <option value="approval_rule">Approval rule</option>
          </select>
          {filters.targetKind && (
            <TargetIdField
              targetKind={filters.targetKind}
              value={filters.targetId}
              onChange={(targetId) => patch({ targetId })}
              modules={modules}
              pages={pages}
              actionTargets={actionTargets}
              pagesById={pagesById}
            />
          )}
        </div>
      </FilterSection>
    </div>
  );
}

function FilterSection({
  label,
  active,
  onReset,
  children,
}: {
  label: string;
  active: boolean;
  onReset: () => void;
  children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <h3
          id={id}
          className="font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted-fg)]/80"
        >
          {label}
        </h3>
        {active && (
          <button
            type="button"
            onClick={onReset}
            className="text-[11px] text-[var(--accent)] transition-colors hover:text-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            reset
          </button>
        )}
      </div>
      {children}
    </section>
  );
}

function FilterChip({
  selected,
  partial,
  mono,
  onClick,
  children,
}: {
  selected: boolean;
  partial?: boolean;
  mono?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
        mono && "font-mono font-normal text-[11px]",
        selected
          ? "border-[var(--accent-border)] bg-[var(--accent-soft)] text-[var(--accent)]"
          : partial
            ? "border-[var(--accent-border)] text-[var(--accent)]"
            : "border-[var(--border)] text-[var(--muted-fg)] hover:border-[var(--border-strong)] hover:text-[var(--fg)]",
      )}
    >
      {children}
    </button>
  );
}

/**
 * Target-id picker that adapts to the chosen target kind: a module / page /
 * action-target <select> or a free-text id <Input> for approval rules.
 */
function TargetIdField({
  targetKind,
  value,
  onChange,
  modules,
  pages,
  actionTargets,
  pagesById,
}: {
  targetKind: string;
  value: string;
  onChange: (value: string) => void;
  modules: Module[];
  pages: Page[];
  actionTargets: ActionTarget[];
  pagesById: Map<string, Page>;
}) {
  if (targetKind === "module") {
    const options = [...modules].sort((a, b) => {
      const pa = pagesById.get(a.page_id)?.name ?? "";
      const pb = pagesById.get(b.page_id)?.name ?? "";
      if (pa !== pb) return pa.localeCompare(pb);
      const ta = a.title?.trim() || a.type;
      const tb = b.title?.trim() || b.type;
      return ta.localeCompare(tb);
    });
    const known = options.some((m) => m.id === value);
    return (
      <select className={SELECT_CLASS} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All modules</option>
        {options.map((m) => {
          const pageName = pagesById.get(m.page_id)?.name;
          const label = m.title?.trim() || m.type;
          return (
            <option key={m.id} value={m.id}>
              {pageName ? `${label} (${pageName})` : label}
            </option>
          );
        })}
        {value && !known && <option value={value}>Unknown module ({value})</option>}
      </select>
    );
  }
  if (targetKind === "page") {
    const options = [...pages].sort((a, b) => a.name.localeCompare(b.name));
    const known = options.some((p) => p.id === value);
    return (
      <select className={SELECT_CLASS} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All pages</option>
        {options.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
        {value && !known && <option value={value}>Unknown page ({value})</option>}
      </select>
    );
  }
  if (targetKind === "action_target") {
    const options = [...actionTargets].sort((a, b) => a.name.localeCompare(b.name));
    const known = options.some((t) => t.id === value);
    return (
      <select className={SELECT_CLASS} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All action targets</option>
        {options.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
        {value && !known && <option value={value}>Unknown target ({value})</option>}
      </select>
    );
  }
  return (
    <Input
      className="h-9"
      placeholder="rule_…"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
