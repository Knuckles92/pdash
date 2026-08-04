"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useChannel } from "@/components/layout/RealtimeProvider";
import { cn } from "@/lib/cn";
import type {
  LogEntry,
  LogStreamConfig,
  LogStreamData,
  Severity,
} from "@/lib/modules/types";
import { relativeTime } from "@/lib/time";

const SEVERITY_ORDER: Severity[] = ["error", "warning", "success", "info", "muted"];

// Status-token severity dots (light/dark aware via globals.css tokens).
const SEVERITY_DOT: Record<Severity, string> = {
  error: "bg-[var(--danger)]",
  warning: "bg-[var(--warning)]",
  success: "bg-[var(--success)]",
  info: "bg-[var(--info)]",
  muted: "bg-[var(--muted-fg)]",
};

function severityDot(s?: Severity | null): string {
  return s ? SEVERITY_DOT[s] : "bg-[var(--border-strong)]";
}

function severityRank(severity?: Severity | null): number {
  if (!severity) return SEVERITY_ORDER.length;
  const i = SEVERITY_ORDER.indexOf(severity);
  return i < 0 ? SEVERITY_ORDER.length : i;
}

// Filter by user-selected severity floor: show this severity *or worse*.
function passesSeverityFloor(entrySev: Severity | null | undefined, floor: Severity | null): boolean {
  if (!floor) return true;
  return severityRank(entrySev) <= severityRank(floor);
}

export function LogStreamModule({
  data,
  config,
  moduleId,
  preview = false,
}: {
  data: LogStreamData;
  config: LogStreamConfig;
  moduleId?: string;
  preview?: boolean;
}) {
  const monospace = config.monospace ?? true;
  const showSource = config.show_source ?? true;
  const order = config.order ?? "newest-first";
  const ringBufferSize = config.ring_buffer_size ?? 200;
  const [filter, setFilter] = useState<Severity | null>(
    config.default_filter_severity ?? null,
  );
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [appended, setAppended] = useState<LogEntry[]>([]);

  // Reset appended entries when the underlying module data changes (a server
  // refresh has rolled them in).
  useEffect(() => {
    setAppended([]);
  }, [data.entries]);

  // Phase 5: subscribe to log_stream:<module_id> for tail updates.
  useChannel(!preview && moduleId ? `log_stream:${moduleId}` : "", (ev) => {
    if (!moduleId) return;
    if (ev.kind === "log_appended") {
      const newEntries = (ev.payload.entries as LogEntry[] | undefined) ?? [];
      if (newEntries.length === 0) return;
      setAppended((prev) => {
        const next = [...prev, ...newEntries];
        // Trim to ring buffer policy.
        return next.length > ringBufferSize ? next.slice(-ringBufferSize) : next;
      });
    }
  });

  const entries = useMemo(() => {
    const raw = [...(data.entries ?? []), ...appended];
    const filtered = raw.filter((entry) => passesSeverityFloor(entry.severity, filter));
    // Order is descriptive of insertion direction; we always render with the
    // most-recent entry at the bottom in chronological order to make the
    // sticky-bottom behavior natural. If newest-first is requested, reverse.
    const sorted = [...filtered].sort((a, b) =>
      String(a.t).localeCompare(String(b.t)),
    );
    return order === "newest-first" ? sorted.reverse() : sorted;
  }, [data.entries, appended, filter, order]);

  // Auto-scroll-stickiness for oldest-first (chronological) view: when the
  // user is at the bottom, keep them pinned. When they scroll up, show a
  // sticky "N new" pill.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const stickyRef = useRef<boolean>(true);
  const [pendingNew, setPendingNew] = useState<number>(0);
  const lastLenRef = useRef<number>(entries.length);

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const delta = entries.length - lastLenRef.current;
    if (order === "oldest-first") {
      if (stickyRef.current) {
        el.scrollTop = el.scrollHeight;
        setPendingNew(0);
      } else if (delta > 0) {
        setPendingNew((n) => n + delta);
      }
    }
    lastLenRef.current = entries.length;
  }, [entries.length, order]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    function onScroll() {
      const container = containerRef.current;
      if (!container) return;
      const distFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      stickyRef.current = distFromBottom < 16;
      if (stickyRef.current) setPendingNew(0);
    }
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  if (entries.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <Filters filter={filter} setFilter={setFilter} />
        <p className="text-sm text-[var(--muted-fg)] italic">No log entries.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 relative">
      <Filters filter={filter} setFilter={setFilter} />
      <div
        ref={containerRef}
        className={cn(
          "max-h-80 overflow-y-auto overscroll-contain rounded-lg border border-[var(--border)] bg-[var(--bg)]",
          monospace && "font-mono",
        )}
      >
        <ul className="divide-y divide-[var(--border)]">
          {entries.map((entry, i) => {
            const key = `${entry.t}-${i}-${entry.message.slice(0, 16)}`;
            const isExpanded = expanded[key];
            return (
              <li
                key={key}
                className="flex items-start gap-2 px-2 py-1 text-xs cursor-pointer transition-colors hover:bg-[var(--muted)]/60"
                onClick={() =>
                  setExpanded((m) => ({ ...m, [key]: !m[key] }))
                }
              >
                <span
                  className={cn(
                    "mt-1 size-1.5 rounded-full shrink-0",
                    severityDot(entry.severity),
                  )}
                  aria-label={entry.severity ?? "no severity"}
                />
                <span className="text-[var(--muted-fg)] tabular-nums shrink-0">
                  {relativeTime(entry.t)}
                </span>
                {showSource && entry.source ? (
                  <span className="text-[10px] font-medium uppercase tracking-[0.08em] px-1.5 rounded-full bg-[var(--muted)] text-[var(--muted-fg)] shrink-0">
                    {entry.source}
                  </span>
                ) : null}
                <span
                  className={cn(
                    "min-w-0 break-words",
                    !isExpanded && "truncate",
                    isExpanded && "whitespace-pre-wrap",
                  )}
                  title={!isExpanded ? entry.message : undefined}
                >
                  {entry.message}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
      {pendingNew > 0 && order === "oldest-first" && (
        <button
          type="button"
          className="absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full bg-[var(--accent)] text-[var(--accent-fg)] text-xs font-medium px-3 py-1 shadow-[var(--shadow-md)] transition-colors hover:bg-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
          onClick={() => {
            const el = containerRef.current;
            if (!el) return;
            el.scrollTop = el.scrollHeight;
            stickyRef.current = true;
            setPendingNew(0);
          }}
        >
          {pendingNew} new entr{pendingNew === 1 ? "y" : "ies"}
        </button>
      )}
    </div>
  );
}

function Filters({
  filter,
  setFilter,
}: {
  filter: Severity | null;
  setFilter: (s: Severity | null) => void;
}) {
  return (
    <div className="flex items-center gap-1 text-xs">
      <span className="text-[var(--muted-fg)]">Min severity:</span>
      <select
        value={filter ?? ""}
        onChange={(e) => setFilter((e.target.value || null) as Severity | null)}
        className="rounded-md border border-[var(--border)] bg-[var(--card)] px-1.5 py-0.5 transition-colors hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
      >
        <option value="">all</option>
        <option value="error">error</option>
        <option value="warning">warning</option>
        <option value="success">success</option>
        <option value="info">info</option>
        <option value="muted">muted</option>
      </select>
    </div>
  );
}
