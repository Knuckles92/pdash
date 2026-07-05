"use client";

import Link from "next/link";
import { RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  ActivityFiltersPanel,
  EMPTY_ACTIVITY_FILTERS,
  TIME_PRESETS,
  hasActiveFilters,
  type ActivityFilters,
} from "@/components/activity/ActivityFilters";
import { ActivityRow } from "@/components/activity/ActivityRow";
import { ConsolePath } from "@/components/layout/ConsolePath";
import { useChannel } from "@/components/layout/RealtimeProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Sheet } from "@/components/ui/Sheet";
import {
  api,
  errorMessage,
  type ActionTarget,
  type ActivityLogDetail,
  type ActivityLogRow,
  type Agent,
  type Module,
  type Page,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { indexById } from "@/lib/collections";
import { dayLabel, formatDateTime } from "@/lib/time";

type ActivityViewProps = {
  initialItems: ActivityLogRow[];
  initialNextCursor: string | null;
  agents: Agent[];
  pages: Page[];
  modules: Module[];
  actionTargets: ActionTarget[];
};

export function ActivityView({
  initialItems,
  initialNextCursor,
  agents,
  pages,
  modules,
  actionTargets,
}: ActivityViewProps) {
  const [items, setItems] = useState<ActivityLogRow[]>(initialItems);
  const [nextCursor, setNextCursor] = useState<string | null>(initialNextCursor);
  const [filters, setFilters] = useState<ActivityFilters>(EMPTY_ACTIVITY_FILTERS);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [showMobileFilters, setShowMobileFilters] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [detail, setDetail] = useState<ActivityLogDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [newCount, setNewCount] = useState(0);

  const agentsById = useMemo(() => indexById(agents), [agents]);
  const pagesById = useMemo(() => indexById(pages), [pages]);
  const modulesById = useMemo(() => indexById(modules), [modules]);
  const actionTargetsById = useMemo(() => indexById(actionTargets), [actionTargets]);

  // Debounce free-text search so we don't hit FTS on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setQ(qInput.trim()), 300);
    return () => clearTimeout(t);
  }, [qInput]);

  const fetchPage = useCallback(
    async (opts: { cursor?: string; replace?: boolean }) => {
      const presetMs = TIME_PRESETS.find((p) => p.value === filters.preset)?.ms ?? 0;
      const res = await api.listActivity({
        kind: filters.kinds.size > 0 ? Array.from(filters.kinds).join(",") : undefined,
        outcome:
          filters.outcomes.size > 0 ? Array.from(filters.outcomes).join(",") : undefined,
        actor: filters.actor || undefined,
        target_kind: filters.targetKind || undefined,
        target_id: filters.targetId || undefined,
        q: q || undefined,
        after: presetMs
          ? new Date(Date.now() - presetMs).toISOString()
          : filters.after || undefined,
        before: filters.before || undefined,
        cursor: opts.cursor,
      });
      setItems((prev) => (opts.replace ? res.items : [...prev, ...res.items]));
      setNextCursor(res.next_cursor);
    },
    [filters, q],
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

  // Reload on filter/search change; the initial render already carries page 1.
  const firstRun = useRef(true);
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, q]);

  // Phase 5: count new activity rows arriving via SSE; do NOT auto-prepend
  // (per PLAN — disorienting in a log).
  useChannel("activity", (ev) => {
    if (ev.kind === "activity_appended") {
      setNewCount((c) => c + 1);
    } else if (ev.kind === "resync_required") {
      void reload();
    }
  });

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

  const filtersActive = hasActiveFilters(filters) || !!q;

  // Group rows by calendar day. FTS results are relevance-ordered, so day
  // headers would jumble — fall back to a flat list with dates on each row.
  const searching = !!q;
  const dayGroups = useMemo(() => {
    if (searching) return null;
    const groups: Array<{ label: string; rows: ActivityLogRow[] }> = [];
    for (const row of items) {
      const label = dayLabel(row.timestamp);
      const last = groups[groups.length - 1];
      if (last && last.label === label) last.rows.push(row);
      else groups.push({ label, rows: [row] });
    }
    return groups;
  }, [items, searching]);

  const rowProps = {
    agentsById,
    modulesById,
    pagesById,
    actionTargetsById,
    onActorClick: (actorId: string) => setFilters((f) => ({ ...f, actor: actorId })),
  };

  const clearAll = () => {
    setFilters(EMPTY_ACTIVITY_FILTERS);
    setQInput("");
    setQ("");
  };

  return (
    <div className="flex flex-col gap-4">
      {newCount > 0 && (
        <button
          type="button"
          className="sticky top-2 z-20 self-center rounded-full bg-[var(--accent)] px-3 py-1 text-xs font-medium text-[var(--accent-fg)] shadow-[var(--shadow-md)] transition-colors hover:bg-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]"
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
          <ConsolePath segments={["activity"]} />
          <h1 className="font-display text-xl font-semibold tracking-tight">Activity</h1>
          <p className="text-sm text-[var(--muted-fg)]">
            Audit log of admin + agent decisions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className={cn(
              "lg:hidden",
              showMobileFilters &&
                "bg-[var(--accent-soft)] text-[var(--accent)] hover:bg-[var(--accent-soft)]",
            )}
            onClick={() => setShowMobileFilters((s) => !s)}
            aria-pressed={showMobileFilters}
          >
            <SlidersHorizontal className="size-4" /> Filters
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

      <div className="flex items-start gap-6">
        <aside className="sticky top-6 hidden max-h-[calc(100vh-3rem)] w-56 shrink-0 overflow-y-auto pb-2 lg:block">
          <ActivityFiltersPanel
            filters={filters}
            onChange={setFilters}
            agents={agents}
            modules={modules}
            pages={pages}
            actionTargets={actionTargets}
            pagesById={pagesById}
          />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-[var(--muted-fg)]" />
            <Input
              className="pl-8"
              placeholder="Search the log — actors, targets, ids…"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
            />
          </div>

          {showMobileFilters && (
            <Card className="p-4 lg:hidden">
              <ActivityFiltersPanel
                filters={filters}
                onChange={setFilters}
                agents={agents}
                modules={modules}
                pages={pages}
                actionTargets={actionTargets}
                pagesById={pagesById}
              />
            </Card>
          )}

          <div className="flex items-center justify-between px-1 font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--muted-fg)]/80">
            <span>
              {items.length}
              {nextCursor ? "+" : ""} {items.length === 1 ? "event" : "events"}
              {searching && " · by relevance"}
            </span>
            {filtersActive && (
              <button
                type="button"
                onClick={clearAll}
                className="normal-case tracking-normal text-[var(--accent)] transition-colors hover:text-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              >
                Clear all filters
              </button>
            )}
          </div>

          {items.length === 0 ? (
            <EmptyState
              icon={<Search className="size-6" />}
              title="No activity matches"
              hint={
                filtersActive
                  ? "Loosen the filters or search term to see more history."
                  : "Audit rows land here as soon as agents or admins touch state."
              }
            />
          ) : (
            // overflow-clip (not -hidden) so the sticky day headers still stick
            <Card className="overflow-clip">
              {dayGroups ? (
                dayGroups.map((group, i) => (
                  <section key={group.label} className={cn(i > 0 && "border-t border-[var(--border)]")}>
                    <h2 className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--card)] px-4 py-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted-fg)]/80">
                      {group.label}
                    </h2>
                    {group.rows.map((row) => (
                      <ActivityRow
                        key={row.id}
                        row={row}
                        {...rowProps}
                        onClick={() => void openDetail(row)}
                      />
                    ))}
                  </section>
                ))
              ) : (
                <div className="divide-y divide-[var(--border)]">
                  {items.map((row) => (
                    <ActivityRow
                      key={row.id}
                      row={row}
                      {...rowProps}
                      showDate
                      onClick={() => void openDetail(row)}
                    />
                  ))}
                </div>
              )}
              {nextCursor && (
                <div className="border-t border-[var(--border)] p-3 text-center">
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
        </div>
      </div>

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
            {detail.request_id && <Field label="Request">{detail.request_id}</Field>}
            {detail.rule_id && (
              <Field label="Rule">
                <Link
                  className="text-[var(--accent)] underline underline-offset-2 transition-colors hover:text-[var(--accent-hover)]"
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
                <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
                  Payload {detailLoading ? "(loading…)" : "summary"}
                </div>
                <pre className="mt-1.5 max-h-80 overflow-auto rounded-lg bg-[var(--muted)] p-3 font-mono text-xs leading-relaxed">
                  {JSON.stringify(detail.payload_summary, null, 2)}
                </pre>
              </div>
            )}
            {detail.audit_blob && (
              <div>
                <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
                  Full payload (blob)
                </div>
                <pre className="mt-1.5 max-h-96 overflow-auto rounded-lg bg-[var(--muted)] p-3 font-mono text-xs leading-relaxed">
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-20 shrink-0 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
        {label}
      </span>
      <span className="font-mono text-xs break-all">{children}</span>
    </div>
  );
}
