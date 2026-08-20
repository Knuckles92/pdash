"use client";

import { Check, ChevronDown, ChevronRight, Keyboard, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/time";

import {
  AgentAvatar,
  CompactRow,
  FamilyDots,
  Kbd,
  SelectCheckbox,
  groupRowsByAgent,
  type ApprovalAgentGroup,
  type ApprovalLayoutProps,
} from "./shared";

/**
 * Agent-grouped, keyboard-driven inbox of compact rows. Clicking (or Enter-ing)
 * a row opens the full `ApprovalCard` directly beneath it — the row stays put as
 * an anchor so the queue never re-flows out from under you. Shared by the Triage
 * Inbox and Command Center layouts.
 *
 * Navigation model:
 *   - One keyboard cursor over the *visible* rows (collapsed groups are skipped);
 *     j/k or arrows move it, and moving it prefetches that request's preview so
 *     opening the card is instant.
 *   - The cursor is only created once the admin asks for it, and a/d/x/Enter do
 *     nothing without one — a stray keystroke can never decide a request.
 *   - Group headers stick to the top of the viewport while their rows scroll, so
 *     you always know whose queue you're in.
 *   - Group-wide approve/deny needs a second click to confirm (bulk decisions
 *     have no undo, unlike single-row ones).
 */
export function GroupedInbox({
  rows,
  selectedIds,
  busyIds,
  bulkBusy = false,
  onToggleSelect,
  onApprove,
  onDeny,
  onApproveMany,
  onDenyMany,
  onWantDetail,
  renderCard,
}: ApprovalLayoutProps) {
  const groups = useMemo(() => orderGroups(groupRowsByAgent(rows)), [rows]);

  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [cursorId, setCursorId] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [confirming, setConfirming] = useState<GroupConfirm | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const rowEls = useRef(new Map<string, HTMLDivElement>());
  /** Where the cursor sat last, so a decided row hands it to its neighbour. */
  const cursorIndexRef = useRef(0);

  const allIds = useMemo(() => rows.map((r) => r.request.id), [rows]);
  const visibleIds = useMemo(
    () =>
      groups.flatMap((g) => (collapsed.has(g.key) ? [] : g.rows.map((r) => r.request.id))),
    [groups, collapsed],
  );

  const selectedCount = useMemo(
    () => allIds.filter((id) => selectedIds.has(id)).length,
    [allIds, selectedIds],
  );

  const focusRow = useCallback((id: string) => {
    const el = rowEls.current.get(id);
    if (!el) return;
    el.focus({ preventScroll: true });
    el.scrollIntoView({ block: "nearest" });
  }, []);

  /**
   * Keep the cursor on a row that still exists. When the row under it is
   * approved/denied away, the cursor takes that slot's new occupant so you can
   * hold `a` and walk a queue down without touching the mouse.
   */
  useEffect(() => {
    if (cursorId === null) return;
    const at = visibleIds.indexOf(cursorId);
    if (at !== -1) {
      cursorIndexRef.current = at;
      return;
    }
    if (visibleIds.length === 0) {
      setCursorId(null);
      return;
    }
    const keepFocus = containerRef.current?.contains(document.activeElement) ?? false;
    const next = visibleIds[Math.min(cursorIndexRef.current, visibleIds.length - 1)]!;
    setCursorId(next);
    if (keepFocus) requestAnimationFrame(() => focusRow(next));
  }, [visibleIds, cursorId, focusRow]);

  // A row decided from its expanded card takes its detail view with it.
  useEffect(() => {
    if (expandedId && !allIds.includes(expandedId)) setExpandedId(null);
  }, [allIds, expandedId]);

  const moveCursor = useCallback(
    (delta: number) => {
      if (visibleIds.length === 0) return;
      const from = cursorId ? visibleIds.indexOf(cursorId) : -1;
      const to =
        from === -1
          ? delta > 0
            ? 0
            : visibleIds.length - 1
          : Math.min(visibleIds.length - 1, Math.max(0, from + delta));
      const id = visibleIds[to]!;
      setCursorId(id);
      // Warm the preview for the row you're sitting on.
      onWantDetail(id);
      focusRow(id);
    },
    [visibleIds, cursorId, onWantDetail, focusRow],
  );

  const toggleGroup = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleRow = useCallback(
    (id: string) => {
      setCursorId(id);
      setExpandedId((prev) => {
        if (prev === id) return null;
        onWantDetail(id);
        return id;
      });
    },
    [onWantDetail],
  );

  const groupOf = useCallback(
    (id: string) => groups.find((g) => g.rows.some((r) => r.request.id === id)) ?? null,
    [groups],
  );

  const anyCollapsed = groups.some((g) => collapsed.has(g.key));
  function toggleAllGroups() {
    setCollapsed(anyCollapsed ? new Set() : new Set(groups.map((g) => g.key)));
  }

  function toggleSelectAll() {
    const everySelected = allIds.length > 0 && allIds.every((id) => selectedIds.has(id));
    for (const id of allIds) {
      if (everySelected ? selectedIds.has(id) : !selectedIds.has(id)) onToggleSelect(id);
    }
  }

  function toggleSelectGroup(group: ApprovalAgentGroup) {
    const ids = group.rows.map((r) => r.request.id);
    const everySelected = ids.every((id) => selectedIds.has(id));
    for (const id of ids) {
      if (everySelected ? selectedIds.has(id) : !selectedIds.has(id)) onToggleSelect(id);
    }
  }

  /** First click arms the group action, second click fires it. */
  function pressGroupAction(group: ApprovalAgentGroup, action: "approve" | "deny") {
    if (confirming?.key === group.key && confirming.action === action) {
      const ids = group.rows.map((r) => r.request.id);
      setConfirming(null);
      if (action === "approve") onApproveMany(ids);
      else onDenyMany(ids);
      return;
    }
    setConfirming({ key: group.key, action });
  }

  // --- Keyboard triage ------------------------------------------------------
  // A window-level listener (rather than one scoped to a focused container) so
  // the queue is drivable the moment the page loads. The handler is kept in a
  // ref so the listener is registered once but always sees current state.
  function handleKey(e: KeyboardEvent) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    // Never steal keys from a text field, and never act behind a modal — the
    // rule editor and command palette don't always move focus into themselves,
    // so checking the event target alone isn't enough.
    const target = e.target as HTMLElement | null;
    if (
      target &&
      (target.isContentEditable ||
        /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) ||
        target.closest("[role='dialog']"))
    ) {
      return;
    }
    if (document.querySelector("[role='dialog'][aria-modal='true']")) return;
    // Let a focused control keep its own activation keys (Tab → Approve → Enter
    // must approve, not expand the row). Navigation keys still work from there.
    const onControl = Boolean(target?.closest("button, a[href]"));
    if (onControl && (e.key === "Enter" || e.key === " ")) return;

    switch (e.key) {
      case "j":
      case "ArrowDown":
        e.preventDefault();
        moveCursor(1);
        return;
      case "k":
      case "ArrowUp":
        e.preventDefault();
        moveCursor(-1);
        return;
      case "?":
        e.preventDefault();
        setShowHelp((s) => !s);
        return;
      case "Escape":
        if (confirming) setConfirming(null);
        else if (expandedId) setExpandedId(null);
        return;
      default:
        break;
    }

    // Everything below acts on a row, so it needs an explicit cursor.
    if (!cursorId) return;
    switch (e.key) {
      case "Enter":
      case "o":
      case " ":
        e.preventDefault();
        toggleRow(cursorId);
        break;
      case "a":
        e.preventDefault();
        onApprove(cursorId, false);
        break;
      case "d":
        e.preventDefault();
        onDeny(cursorId, false);
        break;
      case "x":
        e.preventDefault();
        onToggleSelect(cursorId);
        break;
      case "g": {
        e.preventDefault();
        const group = groupOf(cursorId);
        if (group) toggleGroup(group.key);
        break;
      }
      default:
        break;
    }
  }

  const handleKeyRef = useRef(handleKey);
  useEffect(() => {
    handleKeyRef.current = handleKey;
  });
  useEffect(() => {
    const handler = (e: KeyboardEvent) => handleKeyRef.current(e);
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div ref={containerRef} className="flex flex-col gap-2">
      {/* Inbox toolbar — bulk select, group folding, shortcut legend. */}
      <div className="flex items-center gap-2 px-1 text-xs text-[var(--muted-fg)]">
        <SelectCheckbox
          checked={allIds.length > 0 && selectedCount === allIds.length}
          indeterminate={selectedCount > 0}
          label="Select all requests"
          onChange={toggleSelectAll}
        />
        <span className="tabular-nums">
          {selectedCount > 0
            ? `${selectedCount} of ${allIds.length} selected`
            : `${allIds.length} ${allIds.length === 1 ? "request" : "requests"}`}
        </span>
        <span className="hidden sm:inline">
          · {groups.length} {groups.length === 1 ? "agent" : "agents"}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={toggleAllGroups}
            className="rounded-lg px-2 py-1 transition-colors hover:bg-[var(--muted)] hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            {anyCollapsed ? "Expand all" : "Collapse all"}
          </button>
          <button
            type="button"
            onClick={() => setShowHelp((s) => !s)}
            aria-pressed={showHelp}
            title="Keyboard shortcuts (?)"
            aria-label="Keyboard shortcuts"
            className={cn(
              "inline-flex size-7 items-center justify-center rounded-lg transition-colors hover:bg-[var(--muted)] hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
              showHelp && "bg-[var(--accent-soft)] text-[var(--accent)]",
            )}
          >
            <Keyboard className="size-4" />
          </button>
        </div>
      </div>

      {showHelp && <ShortcutLegend />}

      {groups.map((group) => {
        const isCollapsed = collapsed.has(group.key);
        const ids = group.rows.map((r) => r.request.id);
        const selectedHere = ids.filter((id) => selectedIds.has(id)).length;
        const riskCount = group.rows.filter((r) => r.destructive).length;
        const armed = confirming?.key === group.key ? confirming.action : null;
        return (
          <div
            key={group.key}
            className="rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-[var(--shadow-sm)]"
          >
            {/* Sticky so the agent you're triaging stays named while you scroll.
                Offset clears the mobile app bar; desktop has no fixed header. */}
            <div className="sticky top-[3.25rem] z-20 flex items-center gap-2 rounded-t-xl border-b border-[var(--border)] bg-[var(--muted)]/80 px-2 py-1.5 backdrop-blur md:top-0">
              <SelectCheckbox
                checked={selectedHere === ids.length}
                indeterminate={selectedHere > 0}
                label={`Select all from ${group.label}`}
                onChange={() => toggleSelectGroup(group)}
              />
              <button
                type="button"
                onClick={() => toggleGroup(group.key)}
                aria-expanded={!isCollapsed}
                className="-ml-1 flex min-w-0 items-center gap-2 rounded-lg px-1 py-0.5 text-left transition-colors hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              >
                {isCollapsed ? (
                  <ChevronRight className="size-4 shrink-0 text-[var(--muted-fg)]" />
                ) : (
                  <ChevronDown className="size-4 shrink-0 text-[var(--muted-fg)]" />
                )}
                <AgentAvatar agentId={group.agentId} name={group.label} size="sm" />
                <span className="truncate font-medium tracking-tight">{group.label}</span>
                {group.kind === "new" && (
                  <span className="shrink-0 rounded-full border border-[var(--border)] bg-[var(--muted)] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--muted-fg)]">
                    new
                  </span>
                )}
                <span className="shrink-0 rounded-full bg-[var(--muted)] px-1.5 text-xs tabular-nums text-[var(--muted-fg)]">
                  {group.rows.length}
                </span>
              </button>

              <div className="ml-auto flex items-center gap-2">
                <FamilyDots rows={group.rows} className="hidden sm:inline-flex" />
                {riskCount > 0 && (
                  <span className="hidden shrink-0 rounded-full border border-[var(--warning)]/25 bg-[var(--warning-soft)] px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-[var(--warning)] sm:inline">
                    {riskCount} need a look
                  </span>
                )}
                <span className="hidden whitespace-nowrap text-[11px] tabular-nums text-[var(--muted-fg)] md:inline">
                  oldest {relativeTime(oldestCreatedAt(group))}
                </span>
                {armed ? (
                  <div className="flex items-center gap-1">
                    <span className="whitespace-nowrap text-xs text-[var(--muted-fg)]">
                      {armed === "approve" ? "Approve" : "Deny"} all {ids.length}?
                    </span>
                    <button
                      type="button"
                      disabled={bulkBusy}
                      onClick={() => pressGroupAction(group, armed)}
                      className={cn(
                        "inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:pointer-events-none disabled:opacity-40",
                        armed === "approve"
                          ? "bg-[var(--success-soft)] text-[var(--success)]"
                          : "bg-[var(--danger-soft)] text-[var(--danger)]",
                      )}
                    >
                      Confirm
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirming(null)}
                      className="inline-flex h-7 items-center rounded-lg px-2 text-xs text-[var(--muted-fg)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  // A one-row group needs no group actions — its own row buttons
                  // do the same thing, and those come with undo.
                  ids.length > 1 && (
                    <div className="flex items-center gap-1">
                      <GroupAction
                        tone="approve"
                        disabled={bulkBusy}
                        onClick={() => pressGroupAction(group, "approve")}
                      />
                      <GroupAction
                        tone="deny"
                        disabled={bulkBusy}
                        onClick={() => pressGroupAction(group, "deny")}
                      />
                    </div>
                  )
                )}
              </div>
            </div>

            {!isCollapsed && (
              <div role="list" className="flex flex-col gap-0.5 p-1.5">
                {group.rows.map((vm) => {
                  const id = vm.request.id;
                  const isExpanded = expandedId === id;
                  return (
                    <div key={id} role="listitem" className="flex flex-col">
                      <CompactRow
                        vm={vm}
                        expanded={isExpanded}
                        cursor={cursorId === id}
                        busy={busyIds.has(id)}
                        selected={selectedIds.has(id)}
                        tabIndex={cursorId === id ? 0 : -1}
                        elementRef={(el) => {
                          if (el) rowEls.current.set(id, el);
                          else rowEls.current.delete(id);
                        }}
                        onToggleSelect={() => onToggleSelect(id)}
                        onClick={() => toggleRow(id)}
                        onApprove={() => onApprove(id, false)}
                        onDeny={() => onDeny(id, false)}
                      />
                      {isExpanded && (
                        <div className="anim-fade-up px-1 pb-1 pt-1.5">
                          {renderCard(vm.request, { defaultExpanded: true })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

type GroupConfirm = { key: string; action: "approve" | "deny" };

function GroupAction({
  tone,
  disabled,
  onClick,
}: {
  tone: "approve" | "deny";
  disabled?: boolean;
  onClick: () => void;
}) {
  const approve = tone === "approve";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={approve ? "Approve every request from this agent" : "Deny every request from this agent"}
      className={cn(
        "inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:pointer-events-none disabled:opacity-40",
        approve
          ? "text-[var(--success)] hover:bg-[var(--success-soft)]"
          : "text-[var(--danger)] hover:bg-[var(--danger-soft)]",
      )}
    >
      {approve ? <Check className="size-3.5" /> : <X className="size-3.5" />}
      <span className="hidden sm:inline">{approve ? "Approve all" : "Deny all"}</span>
    </button>
  );
}

function ShortcutLegend() {
  const items: Array<[string, string]> = [
    ["j / k", "move"],
    ["Enter", "open"],
    ["a", "approve"],
    ["d", "deny"],
    ["x", "select"],
    ["g", "fold group"],
    ["Esc", "close"],
  ];
  return (
    <div className="anim-fade-up flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-[var(--border)] bg-[var(--muted)]/40 px-3 py-2 text-xs text-[var(--muted-fg)]">
      {items.map(([keys, what]) => (
        <span key={keys} className="inline-flex items-center gap-1.5">
          {keys.split(" / ").map((k) => (
            <Kbd key={k}>{k}</Kbd>
          ))}
          {what}
        </span>
      ))}
    </div>
  );
}

/** Oldest request in a group — ids are ULIDs, but compare timestamps directly. */
function oldestCreatedAt(group: ApprovalAgentGroup): string {
  return group.rows.reduce(
    (oldest, r) => (r.request.created_at < oldest ? r.request.created_at : oldest),
    group.rows[0]!.request.created_at,
  );
}

/**
 * Stable group order: agent registrations first (they're the security gate, and
 * nothing else can be reviewed on behalf of an agent that isn't trusted yet),
 * then longest-waiting queue first. Deriving it from timestamps rather than
 * first-seen order keeps groups from reshuffling as rows are decided away.
 */
function orderGroups(groups: ApprovalAgentGroup[]): ApprovalAgentGroup[] {
  return groups.slice().sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "new" ? -1 : 1;
    const ageCmp = oldestCreatedAt(a).localeCompare(oldestCreatedAt(b));
    return ageCmp !== 0 ? ageCmp : a.label.localeCompare(b.label);
  });
}
