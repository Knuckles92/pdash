"use client";

import { CheckCircle2, Filter, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { ApprovalCard } from "@/components/approvals/ApprovalCard";
import { BulkActionBar } from "@/components/approvals/BulkActionBar";
import {
  buildRows,
  getLayout,
  type ApprovalLayoutProps,
} from "@/components/approvals/layouts";
import { LayoutSwitcher } from "@/components/approvals/layouts/LayoutSwitcher";
import { useApprovalLayout } from "@/components/approvals/layouts/useApprovalLayout";
import { RuleEditor } from "@/components/approvals/RuleEditor";
import { ConsolePath } from "@/components/layout/ConsolePath";
import { useChannel } from "@/components/layout/RealtimeProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  APPROVAL_ACTION_TYPES,
  api,
  errorMessage,
  type ActionPreview,
  type Agent,
  type ApprovalActionType,
  type ApprovalRequest,
  type ApprovalRuleDraft,
  type DashboardPreview,
  type FilePreview,
  type RegistrationPreview,
  type IframeAllowlistEntry,
  type Module,
  type Page,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { indexById } from "@/lib/collections";
import {
  adjustApprovalCount,
  refreshApprovalCount,
} from "@/lib/hooks/useApprovalCount";

type Filters = {
  agent_id: string;
  action_type: string;
  page_id: string;
  created_after: string;
  created_before: string;
};

const EMPTY_FILTERS: Filters = {
  agent_id: "",
  action_type: "",
  page_id: "",
  created_after: "",
  created_before: "",
};

type RuleDialogState =
  | { open: false }
  | {
      open: true;
      draft: Partial<ApprovalRuleDraft>;
      requestId: string;
      decideAfterSave: "approve" | null;
    };

type ApprovalsViewProps = {
  initialRequests: ApprovalRequest[];
  initialNextCursor: string | null;
  initialTotalPending: number | null;
  agents: Agent[];
  pages: Page[];
  iframeAllowlist?: IframeAllowlistEntry[];
};

export function ApprovalsView({
  initialRequests,
  initialNextCursor,
  initialTotalPending,
  agents,
  pages,
  iframeAllowlist = [],
}: ApprovalsViewProps) {
  const [requests, setRequests] = useState<ApprovalRequest[]>(initialRequests);
  const [nextCursor, setNextCursor] = useState<string | null>(initialNextCursor);
  const [totalPending, setTotalPending] = useState<number | null>(initialTotalPending);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [diffPreviews, setDiffPreviews] = useState<Map<string, Record<string, unknown>>>(
    new Map(),
  );
  const [dashboardPreviews, setDashboardPreviews] = useState<Map<string, DashboardPreview>>(
    new Map(),
  );
  const [actionPreviews, setActionPreviews] = useState<Map<string, ActionPreview>>(new Map());
  const [filePreviews, setFilePreviews] = useState<Map<string, FilePreview>>(new Map());
  const [registrationPreviews, setRegistrationPreviews] = useState<
    Map<string, RegistrationPreview>
  >(new Map());
  const [detailLoadingIds, setDetailLoadingIds] = useState<Set<string>>(new Set());
  const [detailFetchedIds, setDetailFetchedIds] = useState<Set<string>>(new Set());
  const [ruleDialog, setRuleDialog] = useState<RuleDialogState>({ open: false });
  const [layoutId, setLayoutId] = useApprovalLayout();

  const agentsById = useMemo(() => indexById(agents), [agents]);

  const pagesById = useMemo(() => indexById(pages), [pages]);

  // Modules referenced by requests — fetched lazily on demand.
  const [modules, setModules] = useState<Map<string, Module>>(new Map());

  // Pre-derive the per-request view model once; layouts render from this.
  const rows = useMemo(
    () => buildRows(requests, agentsById, modules, pagesById),
    [requests, agentsById, modules, pagesById],
  );

  const fetchPage = useCallback(
    async (opts: { cursor?: string; replace?: boolean }) => {
      const res = await api.listApprovalRequests({
        status: "pending",
        agent_id: filters.agent_id || undefined,
        action_type: filters.action_type || undefined,
        page_id: filters.page_id || undefined,
        created_after: filters.created_after || undefined,
        created_before: filters.created_before || undefined,
        cursor: opts.cursor,
        limit: 50,
      });
      setRequests((prev) => (opts.replace ? res.items : [...prev, ...res.items]));
      setNextCursor(res.next_cursor);
      if (res.total_pending !== null && res.total_pending !== undefined) {
        setTotalPending(res.total_pending);
      }
    },
    [filters],
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

  // Phase 5: live SSE updates instead of polling.
  useChannel("approvals", (ev) => {
    if (ev.kind === "approval_pending") {
      // Refetch the head so we get the canonical row shape and filters apply.
      void fetchPage({ replace: true });
    } else if (ev.kind === "approval_decided") {
      const reqId = ev.payload.request_id as string | undefined;
      if (reqId) {
        setRequests((prev) => prev.filter((r) => r.id !== reqId));
        bumpTotalPending(-1);
      }
    } else if (ev.kind === "resync_required") {
      void fetchPage({ replace: true });
    }
  });

  // Re-fetch on mount and filter change (matches ActivityView).
  useEffect(() => {
    void reload();
  }, [filters, reload]);

  // Hydrate referenced modules (so we can show titles + diffs).
  useEffect(() => {
    const needed = new Set<string>();
    for (const r of requests) {
      if (r.target_kind === "module" && r.target_id && !modules.has(r.target_id)) {
        needed.add(r.target_id);
      }
    }
    if (needed.size === 0) return;
    let cancelled = false;
    void (async () => {
      const next = new Map(modules);
      // Cheap: list all modules per affected page. For Phase 3 just fetch a
      // single broad list; we have at most a few pages.
      try {
        const { items } = await api.listModules({});
        for (const m of items) next.set(m.id, m);
        if (!cancelled) setModules(next);
      } catch {
        /* swallow */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [requests, modules]);

  function patchFilter(changes: Partial<Filters>): void {
    setFilters((f) => ({ ...f, ...changes }));
  }

  function bumpTotalPending(delta: number): void {
    setTotalPending((count) => (count == null ? count : Math.max(0, count + delta)));
  }

  function toggleSelect(id: string): void {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function removeFromList(id: string): void {
    setRequests((prev) => prev.filter((r) => r.id !== id));
    setSelected((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    adjustApprovalCount(-1);
    bumpTotalPending(-1);
  }

  function setBusy(id: string, busy: boolean): void {
    setBusyIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function maybeFetchDetail(id: string): Promise<void> {
    if (detailFetchedIds.has(id) || detailLoadingIds.has(id)) {
      return;
    }
    setDetailLoadingIds((prev) => new Set(prev).add(id));
    try {
      const d = await api.getApprovalRequest(id);
      if (d.diff_preview) {
        setDiffPreviews((prev) => {
          const next = new Map(prev);
          next.set(id, d.diff_preview as Record<string, unknown>);
          return next;
        });
      }
      if (d.dashboard_preview) {
        setDashboardPreviews((prev) => {
          const next = new Map(prev);
          next.set(id, d.dashboard_preview as DashboardPreview);
          return next;
        });
      }
      if (d.action_preview) {
        setActionPreviews((prev) => {
          const next = new Map(prev);
          next.set(id, d.action_preview as ActionPreview);
          return next;
        });
      }
      if (d.file_preview) {
        setFilePreviews((prev) => {
          const next = new Map(prev);
          next.set(id, d.file_preview as FilePreview);
          return next;
        });
      }
      if (d.registration_preview) {
        setRegistrationPreviews((prev) => {
          const next = new Map(prev);
          next.set(id, d.registration_preview as RegistrationPreview);
          return next;
        });
      }
    } catch {
      /* ignore */
    } finally {
      setDetailFetchedIds((prev) => new Set(prev).add(id));
      setDetailLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  /** Optimistic approve/deny with 5s undo. */
  async function doDecision(
    request: ApprovalRequest,
    decision: "approve" | "deny",
  ): Promise<void> {
    setBusy(request.id, true);
    const snapshot = request;
    let undone = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let toastId: string | number | undefined;

    const performMutation = async () => {
      try {
        if (decision === "approve") {
          await api.approveRequest(request.id);
        } else {
          await api.denyRequest(request.id);
        }
        refreshApprovalCount();
      } catch (err) {
        toast.error(errorMessage(err, "Failed"));
        // Rollback list.
        setRequests((prev) => {
          if (prev.find((r) => r.id === snapshot.id)) return prev;
          return [snapshot, ...prev];
        });
        adjustApprovalCount(1);
      } finally {
        setBusy(request.id, false);
      }
    };

    removeFromList(request.id);
    toastId = toast(
      decision === "approve" ? "Approved" : "Denied",
      {
        description: snapshot.action_type,
        duration: 5000,
        action: {
          label: "Undo",
          onClick: () => {
            undone = true;
            if (timer) clearTimeout(timer);
            setRequests((prev) => [snapshot, ...prev]);
            adjustApprovalCount(1);
            bumpTotalPending(1);
            if (toastId !== undefined) toast.dismiss(toastId);
            setBusy(request.id, false);
          },
        },
      },
    );
    timer = setTimeout(() => {
      if (!undone) void performMutation();
    }, 5000);
  }

  function draftRuleForRequest(
    request: ApprovalRequest,
    outcome: ApprovalRuleDraft["outcome"],
  ): Partial<ApprovalRuleDraft> {
    // Compute the narrowest draft per PLAN §7.4.
    const draft: Partial<ApprovalRuleDraft> = {
      agent_id: request.agent_id ?? "*",
      action_type: request.action_type,
      outcome,
      priority: 100,
      enabled: true,
    };
    if (request.target_kind === "module" && request.target_id) {
      draft.module_id = request.target_id;
    } else if (request.target_kind === "page" && request.target_id) {
      draft.page_id = request.target_id;
    } else if (
      request.action_type === "create_module" ||
      request.action_type === "create_page"
    ) {
      const t = (request.proposed_payload?.type as string | undefined) ?? null;
      if (t) draft.module_type = t;
    }
    return draft;
  }

  /** Approve the current request and create a future auto-approval rule. */
  function openApproveFutureFlow(request: ApprovalRequest): void {
    setRuleDialog({
      open: true,
      draft: draftRuleForRequest(request, "auto_approve"),
      requestId: request.id,
      decideAfterSave: "approve",
    });
  }

  /** Open rule editing from the request without deciding the request itself. */
  function openAdjustRulesFlow(request: ApprovalRequest): void {
    setRuleDialog({
      open: true,
      draft: draftRuleForRequest(request, "prompt"),
      requestId: request.id,
      decideAfterSave: null,
    });
  }

  /** Bulk-decide an explicit set of ids (no per-item undo — used by the
   * bulk bar and by layout group "approve/deny all" buttons). */
  async function decideIds(ids: string[], decision: "approve" | "deny"): Promise<void> {
    if (ids.length === 0) return;
    const idSet = new Set(ids);
    setBulkBusy(true);
    const snapshot = requests.filter((r) => idSet.has(r.id));
    try {
      const res = await api.bulkDecideRequests(ids.map((id) => ({ id, decision })));
      const removedIds = new Set(
        res.results
          .filter((r) => r.error == null && r.status !== "not_found")
          .map((r) => r.id),
      );
      setRequests((prev) => prev.filter((r) => !removedIds.has(r.id)));
      adjustApprovalCount(-removedIds.size);
      bumpTotalPending(-removedIds.size);
      setSelected((prev) => {
        const next = new Set(prev);
        for (const id of removedIds) next.delete(id);
        return next;
      });
      const errors = res.results.filter((r) => r.error);
      if (errors.length > 0) {
        toast.error(`${errors.length} failed`, { description: errors[0]?.error ?? undefined });
      } else {
        toast.success(`${removedIds.size} ${decision === "approve" ? "approved" : "denied"}`);
      }
      refreshApprovalCount();
    } catch (err) {
      toast.error(errorMessage(err, "Bulk failed"));
      // Restore list optimistically (best-effort).
      setRequests((prev) => {
        const have = new Set(prev.map((r) => r.id));
        return [...snapshot.filter((s) => !have.has(s.id)), ...prev];
      });
    } finally {
      setBulkBusy(false);
    }
  }

  function bulkDecide(decision: "approve" | "deny"): void {
    void decideIds(Array.from(selected), decision);
  }

  const visibleAgents = useMemo(
    () => agents.filter((a) => a.status !== "revoked"),
    [agents],
  );

  function handleDecision(id: string, decision: "approve" | "deny", withRule: boolean): void {
    const request = requests.find((r) => r.id === id);
    if (!request) return;
    if (withRule && decision === "approve") openApproveFutureFlow(request);
    else void doDecision(request, decision);
  }

  function handleAdjustRules(id: string): void {
    const request = requests.find((r) => r.id === id);
    if (!request) return;
    openAdjustRulesFlow(request);
  }

  /** A fully-wired ApprovalCard — the detail/expanded view used by every layout. */
  function renderCard(
    request: ApprovalRequest,
    opts?: { defaultExpanded?: boolean },
  ): ReactNode {
    return (
      <div onMouseEnter={() => void maybeFetchDetail(request.id)}>
        <ApprovalCard
          request={request}
          diffPreview={diffPreviews.get(request.id)}
          dashboardPreview={dashboardPreviews.get(request.id) ?? null}
          actionPreview={actionPreviews.get(request.id) ?? null}
          filePreview={filePreviews.get(request.id) ?? null}
          registrationPreview={registrationPreviews.get(request.id) ?? null}
          detailLoading={detailLoadingIds.has(request.id)}
          detailFetched={detailFetchedIds.has(request.id)}
          defaultExpanded={opts?.defaultExpanded}
          iframeAllowlist={iframeAllowlist}
          selected={selected.has(request.id)}
          onToggleSelect={() => toggleSelect(request.id)}
          onExpand={() => void maybeFetchDetail(request.id)}
          agentsById={agentsById}
          modulesById={modules}
          pagesById={pagesById}
          busy={busyIds.has(request.id)}
          onApprove={(withRule) => handleDecision(request.id, "approve", withRule)}
          onDeny={() => handleDecision(request.id, "deny", false)}
          onAdjustRules={() => handleAdjustRules(request.id)}
          onLongPress={() => toggleSelect(request.id)}
        />
      </div>
    );
  }

  const layoutProps: ApprovalLayoutProps = {
    rows,
    agents,
    selectedIds: selected,
    busyIds,
    onToggleSelect: toggleSelect,
    onApprove: (id, withRule) => handleDecision(id, "approve", withRule),
    onDeny: (id, withRule) => handleDecision(id, "deny", withRule),
    onApproveMany: (ids) => void decideIds(ids, "approve"),
    onDenyMany: (ids) => void decideIds(ids, "deny"),
    onWantDetail: (id) => void maybeFetchDetail(id),
    renderCard,
  };

  const ActiveLayout = getLayout(layoutId).Component;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <ConsolePath segments={["approvals"]} />
          <h1 className="font-display text-xl font-semibold tracking-tight">Approvals</h1>
          <p className="text-sm text-[var(--muted-fg)]">
            {totalPending != null
              ? `${totalPending} pending`
              : `${requests.length} loaded`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <LayoutSwitcher value={layoutId} onChange={setLayoutId} />
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

      {showFilters && (
        <Card className="p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            <label className="flex flex-col gap-1 text-xs">
              <span className="font-medium text-[var(--muted-fg)]">Agent</span>
              <select
                className="h-9 rounded-lg border border-[var(--border-strong)] bg-[var(--bg)] px-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                value={filters.agent_id}
                onChange={(e) => patchFilter({ agent_id: e.target.value })}
              >
                <option value="">All agents</option>
                {visibleAgents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="font-medium text-[var(--muted-fg)]">Page</span>
              <select
                className="h-9 rounded-lg border border-[var(--border-strong)] bg-[var(--bg)] px-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                value={filters.page_id}
                onChange={(e) => patchFilter({ page_id: e.target.value })}
              >
                <option value="">All pages</option>
                {pages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="font-medium text-[var(--muted-fg)]">After</span>
              <input
                type="datetime-local"
                className="h-9 rounded-lg border border-[var(--border-strong)] bg-[var(--bg)] px-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                value={filters.created_after}
                onChange={(e) => patchFilter({ created_after: e.target.value })}
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <button
              type="button"
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                filters.action_type === ""
                  ? "border-[var(--accent-border)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--muted-fg)] hover:border-[var(--border-strong)] hover:text-[var(--fg)]",
              )}
              onClick={() => patchFilter({ action_type: "" })}
            >
              all actions
            </button>
            {APPROVAL_ACTION_TYPES.map((at) => (
              <button
                key={at}
                type="button"
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                  filters.action_type === at
                    ? "border-[var(--accent-border)] bg-[var(--accent-soft)] text-[var(--accent)]"
                    : "border-[var(--border)] text-[var(--muted-fg)] hover:border-[var(--border-strong)] hover:text-[var(--fg)]",
                )}
                onClick={() =>
                  patchFilter({
                    action_type: filters.action_type === at ? "" : (at as ApprovalActionType),
                  })
                }
              >
                {at}
              </button>
            ))}
          </div>
        </Card>
      )}

      {requests.length === 0 ? (
        <EmptyState
          icon={<CheckCircle2 className="size-6 text-[var(--success)]" />}
          title="Inbox zero"
          hint="No pending requests right now. Agents will queue up here when they need a decision."
        />
      ) : (
        <div className="flex flex-col gap-2">
          <ActiveLayout {...layoutProps} />
          {nextCursor && (
            <div className="flex justify-center">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void fetchPage({ cursor: nextCursor })}
              >
                Load more
              </Button>
            </div>
          )}
        </div>
      )}

      <BulkActionBar
        count={selected.size}
        busy={bulkBusy}
        onApproveAll={() => void bulkDecide("approve")}
        onDenyAll={() => void bulkDecide("deny")}
        onClear={() => setSelected(new Set())}
      />

      {ruleDialog.open && (
        <RuleEditor
          open={ruleDialog.open}
          onClose={() => setRuleDialog({ open: false })}
          mode={{ kind: "create", draft: ruleDialog.draft }}
          agents={agents}
          pages={pages}
          pendingMatchCount={
            requests.filter((r) => r.action_type === ruleDialog.draft.action_type).length
          }
          onSaved={async () => {
            // Auto-approve future is a compound action: create the rule, then
            // approve the request that prompted it. Adjust Rules only saves.
            if (ruleDialog.decideAfterSave === null) {
              return;
            }
            const requestId = ruleDialog.requestId;
            const target = requests.find((r) => r.id === requestId);
            if (!target) return;
            try {
              if (ruleDialog.decideAfterSave === "approve") {
                await api.approveRequest(requestId);
                toast.success("Approved");
              }
              removeFromList(requestId);
              refreshApprovalCount();
            } catch (err) {
              toast.error(errorMessage(err, "Decision failed"));
            }
          }}
        />
      )}
    </div>
  );
}
