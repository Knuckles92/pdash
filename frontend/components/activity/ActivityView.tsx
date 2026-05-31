"use client";

import Link from "next/link";
import { Filter, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ActivityRow } from "@/components/activity/ActivityRow";
import { useChannel } from "@/components/layout/RealtimeProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Sheet } from "@/components/ui/Sheet";
import {
  api,
  errorMessage,
  type ActivityLogDetail,
  type ActivityLogRow,
  type Agent,
  type Module,
  type Page,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { indexById } from "@/lib/collections";
import { formatDateTime } from "@/lib/time";

type Filters = {
  kind: string;
  actor: string;
  target_kind: string;
  target_id: string;
  q: string;
  after: string;
  before: string;
};

const EMPTY_FILTERS: Filters = {
  kind: "",
  actor: "",
  target_kind: "",
  target_id: "",
  q: "",
  after: "",
  before: "",
};

const SELECT_CLASS =
  "h-9 rounded-md border border-[var(--border)] bg-[var(--bg)] px-2 text-sm w-full";

const KIND_OPTIONS = [
  "create_module",
  "update_module_data",
  "update_module_config",
  "update_module_meta",
  "delete_module",
  "create_page",
  "delete_page",
  "fire_action_button",
  "create_approval_rule",
  "update_approval_rule",
  "delete_approval_rule",
  "revoke_approval_rule",
];

type ActivityViewProps = {
  initialItems: ActivityLogRow[];
  initialNextCursor: string | null;
  agents: Agent[];
  pages: Page[];
  modules: Module[];
};

export function ActivityView({
  initialItems,
  initialNextCursor,
  agents,
  pages,
  modules,
}: ActivityViewProps) {
  const [items, setItems] = useState<ActivityLogRow[]>(initialItems);
  const [nextCursor, setNextCursor] = useState<string | null>(initialNextCursor);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedKinds, setSelectedKinds] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<ActivityLogDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [newCount, setNewCount] = useState(0);

  const agentsById = useMemo(() => indexById(agents), [agents]);
  const pagesById = useMemo(() => indexById(pages), [pages]);
  const modulesById = useMemo(() => indexById(modules), [modules]);

  const moduleFilterOptions = useMemo(() => {
    return [...modules].sort((a, b) => {
      const pa = pagesById.get(a.page_id)?.name ?? "";
      const pb = pagesById.get(b.page_id)?.name ?? "";
      if (pa !== pb) return pa.localeCompare(pb);
      const ta = a.title?.trim() || a.type;
      const tb = b.title?.trim() || b.type;
      return ta.localeCompare(tb);
    });
  }, [modules, pagesById]);

  const pageFilterOptions = useMemo(
    () => [...pages].sort((a, b) => a.name.localeCompare(b.name)),
    [pages],
  );

  const targetIdIsKnown =
    filters.target_kind === "module"
      ? moduleFilterOptions.some((m) => m.id === filters.target_id)
      : filters.target_kind === "page"
        ? pageFilterOptions.some((p) => p.id === filters.target_id)
        : true;

  const fetchPage = useCallback(
    async (opts: { cursor?: string; replace?: boolean }) => {
      const kindCsv =
        selectedKinds.size > 0 ? Array.from(selectedKinds).join(",") : filters.kind || undefined;
      const res = await api.listActivity({
        kind: kindCsv || undefined,
        actor: filters.actor || undefined,
        target_kind: filters.target_kind || undefined,
        target_id: filters.target_id || undefined,
        q: filters.q || undefined,
        after: filters.after || undefined,
        before: filters.before || undefined,
        cursor: opts.cursor,
      });
      setItems((prev) => (opts.replace ? res.items : [...prev, ...res.items]));
      setNextCursor(res.next_cursor);
    },
    [filters, selectedKinds],
  );

  const reload = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetchPage({ replace: true });
    } catch (err) {
      toast.error(errorMessage(err, "Refresh failed"));
    } finally {
      setRefreshing(false);
    }
  }, [fetchPage]);

  // Reload on filter change.
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, selectedKinds]);

  // Phase 5: count new activity rows arriving via SSE; do NOT auto-prepend
  // (per PLAN — disorienting in a log).
  useChannel("activity", (ev) => {
    if (ev.kind === "activity_appended") {
      setNewCount((c) => c + 1);
    } else if (ev.kind === "resync_required") {
      void reload();
    }
  });

  function toggleKind(k: string): void {
    setSelectedKinds((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  async function openDetail(row: ActivityLogRow): Promise<void> {
    setDetail({ ...row });
    setDetailLoading(true);
    try {
      const full = await api.getActivity(row.id);
      setDetail(full);
    } catch {
      /* keep stub */
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {newCount > 0 && (
        <button
          type="button"
          className="sticky top-2 z-20 self-center rounded-full bg-[var(--accent)] text-[var(--accent-fg)] px-3 py-1 text-xs shadow"
          onClick={() => {
            setNewCount(0);
            void reload();
          }}
        >
          {newCount} new {newCount === 1 ? "entry" : "entries"} — show
        </button>
      )}
      <header className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Activity</h1>
          <p className="text-sm text-[var(--muted-fg)]">
            Audit log of admin + agent decisions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowFilters((s) => !s)}
            aria-pressed={showFilters}
          >
            <Filter className="size-4" /> Filters
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void reload()}
            disabled={refreshing}
            aria-label="Refresh"
          >
            <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
          </Button>
        </div>
      </header>

      <div className="relative">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-4 text-[var(--muted-fg)]" />
        <Input
          className="pl-8"
          placeholder="Search payload…"
          value={filters.q}
          onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
        />
      </div>

      {showFilters && (
        <Card className="p-3 flex flex-col gap-2">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--muted-fg)]">Actor</span>
              <Input
                className="h-9"
                list="activity-actor-suggestions"
                placeholder="All actors"
                value={filters.actor}
                onChange={(e) => setFilters((f) => ({ ...f, actor: e.target.value }))}
              />
              <datalist id="activity-actor-suggestions">
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.display_name}
                  </option>
                ))}
              </datalist>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--muted-fg)]">Target kind</span>
              <select
                className={SELECT_CLASS}
                value={filters.target_kind}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    target_kind: e.target.value,
                    target_id: "",
                  }))
                }
              >
                <option value="">all</option>
                <option value="module">module</option>
                <option value="page">page</option>
                <option value="action_target">action_target</option>
                <option value="approval_rule">approval_rule</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--muted-fg)]">
                {filters.target_kind === "module"
                  ? "Module"
                  : filters.target_kind === "page"
                    ? "Page"
                    : "Target id"}
              </span>
              <TargetIdField
                targetKind={filters.target_kind}
                value={filters.target_id}
                onChange={(value) =>
                  setFilters((f) => ({ ...f, target_id: value }))
                }
                moduleOptions={moduleFilterOptions}
                pageOptions={pageFilterOptions}
                pagesById={pagesById}
                isKnown={targetIdIsKnown}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--muted-fg)]">After</span>
              <input
                type="datetime-local"
                className={SELECT_CLASS}
                value={filters.after}
                onChange={(e) => setFilters((f) => ({ ...f, after: e.target.value }))}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--muted-fg)]">Before</span>
              <input
                type="datetime-local"
                className={SELECT_CLASS}
                value={filters.before}
                onChange={(e) => setFilters((f) => ({ ...f, before: e.target.value }))}
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {KIND_OPTIONS.map((k) => (
              <button
                key={k}
                type="button"
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs",
                  selectedKinds.has(k)
                    ? "bg-[var(--accent)] text-[var(--accent-fg)] border-transparent"
                    : "border-[var(--border)] text-[var(--muted-fg)]",
                )}
                onClick={() => toggleKind(k)}
              >
                {k}
              </button>
            ))}
          </div>
        </Card>
      )}

      {items.length === 0 ? (
        <EmptyState
          icon={<Filter className="size-12" />}
          title="No activity matches"
          hint={
            filters.q || selectedKinds.size > 0
              ? "Loosen the filters or search term to see more history."
              : "Audit rows land here as soon as agents or admins touch state."
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="divide-y divide-[var(--border)]">
            {items.map((row) => (
              <ActivityRow
                key={row.id}
                row={row}
                agentsById={agentsById}
                modulesById={modulesById}
                pagesById={pagesById}
                onClick={() => void openDetail(row)}
              />
            ))}
          </div>
          {nextCursor && (
            <div className="p-2 text-center">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void fetchPage({ cursor: nextCursor })}
              >
                Load more
              </Button>
            </div>
          )}
        </Card>
      )}

      <Sheet
        open={!!detail}
        onClose={() => setDetail(null)}
        side="right"
        title={detail ? `Activity #${detail.id}` : ""}
        description={detail ? formatDateTime(detail.timestamp) : undefined}
      >
        {detail && (
          <div className="flex flex-col gap-3 text-sm">
            <Field label="Action">{detail.action_type}</Field>
            <Field label="Actor">{`${detail.actor_kind}${detail.actor_id ? ":" + detail.actor_id : ""}`}</Field>
            <Field label="Outcome">{detail.outcome}</Field>
            {detail.target_kind && (
              <Field label="Target">{`${detail.target_kind}:${detail.target_id ?? ""}`}</Field>
            )}
            {detail.request_id && (
              <Field label="Request">{detail.request_id}</Field>
            )}
            {detail.rule_id && (
              <Field label="Rule">
                <Link
                  className="underline"
                  href={`/settings/rules?id=${detail.rule_id}`}
                  onClick={() => setDetail(null)}
                >
                  {detail.rule_id}
                </Link>
              </Field>
            )}
            {detail.error_detail && (
              <Field label="Error">
                <code className="text-xs text-[var(--danger)]">{detail.error_detail}</code>
              </Field>
            )}
            {detail.payload_summary && (
              <div>
                <div className="text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">
                  Payload {detailLoading ? "(loading…)" : "summary"}
                </div>
                <pre className="mt-1 max-h-80 overflow-auto rounded-md bg-[var(--muted)] p-2 text-[11px]">
                  {JSON.stringify(detail.payload_summary, null, 2)}
                </pre>
              </div>
            )}
            {detail.audit_blob && (
              <div>
                <div className="text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">
                  Full payload (blob)
                </div>
                <pre className="mt-1 max-h-96 overflow-auto rounded-md bg-[var(--muted)] p-2 text-[11px]">
                  {JSON.stringify(detail.audit_blob, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Sheet>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-20 shrink-0 text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">
        {label}
      </span>
      <span className="font-mono text-xs break-all">{children}</span>
    </div>
  );
}

/**
 * Target-id picker that adapts to the chosen target kind: a module/page
 * <select> (with an "Unknown X (id)" fallback when the current id isn't in the
 * options) or a free-text id <Input> for every other kind.
 */
function TargetIdField({
  targetKind,
  value,
  onChange,
  moduleOptions,
  pageOptions,
  pagesById,
  isKnown,
}: {
  targetKind: string;
  value: string;
  onChange: (value: string) => void;
  moduleOptions: Module[];
  pageOptions: Page[];
  pagesById: Map<string, Page>;
  isKnown: boolean;
}) {
  if (targetKind === "module") {
    return (
      <select
        className={SELECT_CLASS}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">All modules</option>
        {moduleOptions.map((m) => {
          const pageName = pagesById.get(m.page_id)?.name;
          const label = m.title?.trim() || m.type;
          return (
            <option key={m.id} value={m.id}>
              {pageName ? `${label} (${pageName})` : label}
            </option>
          );
        })}
        {value && !isKnown && (
          <option value={value}>Unknown module ({value})</option>
        )}
      </select>
    );
  }
  if (targetKind === "page") {
    return (
      <select
        className={SELECT_CLASS}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">All pages</option>
        {pageOptions.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
        {value && !isKnown && (
          <option value={value}>Unknown page ({value})</option>
        )}
      </select>
    );
  }
  return (
    <Input
      placeholder={
        targetKind === "action_target"
          ? "act_…"
          : targetKind === "approval_rule"
            ? "rule_…"
            : "mod_… / pg_…"
      }
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
