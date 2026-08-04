"use client";

import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { safeHref } from "@/lib/modules/safehref";
import { severityChipClass } from "@/lib/modules/severity";
import { formatDateTime } from "@/lib/time";
import type {
  Severity,
  TableCell,
  TableCellRich,
  TableColumn,
  TableConfig,
  TableData,
  TableRow,
} from "@/lib/modules/types";

// Row tints (chips use the shared severityChipClass helper).
const SEVERITY_ROW: Record<Severity, string> = {
  error: "bg-[var(--danger-soft)]",
  warning: "bg-[var(--warning-soft)]",
  success: "bg-[var(--success-soft)]",
  info: "bg-[var(--info-soft)]",
  muted: "bg-[var(--muted)]/60",
};

function isRich(cell: TableCell): cell is TableCellRich {
  return cell !== null && typeof cell === "object";
}

function renderCell(col: TableColumn, cell: TableCell) {
  if (cell === null || cell === undefined) return <span className="text-[var(--muted-fg)]">—</span>;

  switch (col.type) {
    case "severity": {
      const sev = isRich(cell) ? (cell.severity ?? cell.text) : cell;
      return (
        <span
          className={cn(
            "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
            severityChipClass(typeof sev === "string" ? sev : null),
          )}
        >
          {isRich(cell) ? cell.text ?? sev : String(cell)}
        </span>
      );
    }
    case "link": {
      const href = safeHref(isRich(cell) ? cell.href : String(cell));
      const text = isRich(cell) ? cell.text ?? cell.href ?? "" : String(cell);
      if (!href) return <span>{text}</span>;
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded text-[var(--accent)] transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        >
          {text} <ExternalLink className="size-3" />
        </a>
      );
    }
    case "timestamp": {
      const v = isRich(cell) ? cell.text : String(cell);
      return <span className="font-mono text-xs">{formatDateTime(v ?? null)}</span>;
    }
    case "action": {
      const text = isRich(cell) ? cell.text ?? "Run" : String(cell);
      return (
        <Button
          variant="secondary"
          size="sm"
          disabled
          title="Action buttons land in Phase 4"
        >
          {text}
        </Button>
      );
    }
    case "icon": {
      // Phase 2: render as text label; full icon set requires lucide name lookup.
      const text = isRich(cell) ? cell.text ?? cell.icon ?? "" : String(cell);
      return <span className="text-xs text-[var(--muted-fg)]">{text}</span>;
    }
    case "number":
      return (
        <span className="font-mono text-right tabular-nums">
          {isRich(cell) ? cell.text : String(cell)}
        </span>
      );
    case "text":
    default:
      return <span>{isRich(cell) ? cell.text ?? "" : String(cell)}</span>;
  }
}

const densityRowClass: Record<NonNullable<TableConfig["row_density"]>, string> = {
  compact: "py-1",
  normal: "py-2",
  comfortable: "py-3",
};

export function TableModule({ data, config }: { data: TableData; config: TableConfig }) {
  const cols = data.columns ?? [];
  const rows = data.rows ?? [];
  const density = densityRowClass[config.row_density ?? "normal"];
  const mobileLayout = config.mobile_layout ?? "scroll";

  if (rows.length === 0) {
    return (
      <p className="text-sm text-[var(--muted-fg)] italic">
        {config.empty_message ?? "No rows."}
      </p>
    );
  }

  // Card stack: mobile gets stacked cards, desktop gets table
  if (mobileLayout === "card-stack") {
    return (
      <>
        <div className="md:hidden flex flex-col gap-2">
          {rows.map((row, ri) => (
            <CardRow key={row.row_id ?? ri} row={row} cols={cols} />
          ))}
        </div>
        <div className="hidden md:block overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--card)]">
          <DesktopTable rows={rows} cols={cols} density={density} />
        </div>
      </>
    );
  }

  // scroll: just put it in a scrollable container on all sizes
  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--card)]">
      <DesktopTable rows={rows} cols={cols} density={density} />
    </div>
  );
}

function DesktopTable({
  rows,
  cols,
  density,
}: {
  rows: TableRow[];
  cols: TableColumn[];
  density: string;
}) {
  return (
    <table className="w-full text-sm border-collapse">
      <thead className="border-b border-[var(--border)] bg-[var(--muted)]/60">
        <tr>
          {cols.map((c) => (
            <th
              key={c.id}
              className={cn(
                "text-left text-xs uppercase tracking-wide text-[var(--muted-fg)] font-medium px-3 py-2",
                c.hide_on_mobile && "hidden md:table-cell",
                c.align === "right" && "text-right",
                c.align === "center" && "text-center",
              )}
            >
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-[var(--border)]">
        {rows.map((row, ri) => (
          <tr
            key={row.row_id ?? ri}
            className={cn(
              "transition-colors hover:bg-[var(--muted)]/60",
              row.severity && SEVERITY_ROW[row.severity],
            )}
          >
            {cols.map((c) => (
              <td
                key={c.id}
                className={cn(
                  "px-3",
                  density,
                  c.hide_on_mobile && "hidden md:table-cell",
                  c.align === "right" && "text-right",
                  c.align === "center" && "text-center",
                )}
              >
                {renderCell(c, row.cells?.[c.id] ?? null)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CardRow({ row, cols }: { row: TableRow; cols: TableColumn[] }) {
  return (
    <div
      className={cn(
        "rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 flex flex-col gap-1.5",
        row.severity && SEVERITY_ROW[row.severity],
      )}
    >
      {cols.map((c) => (
        <div key={c.id} className="flex items-center justify-between gap-3 text-sm">
          <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
            {c.label}
          </span>
          <span className="text-right">{renderCell(c, row.cells?.[c.id] ?? null)}</span>
        </div>
      ))}
    </div>
  );
}
