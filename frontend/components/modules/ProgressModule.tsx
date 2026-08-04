"use client";

import { cn } from "@/lib/cn";
import type {
  ProgressBar,
  ProgressConfig,
  ProgressData,
  Severity,
} from "@/lib/modules/types";

// Status-token bar fills (light/dark aware via globals.css tokens).
const SEVERITY_FILL: Record<Severity, string> = {
  error: "bg-[var(--danger)]",
  warning: "bg-[var(--warning)]",
  success: "bg-[var(--success)]",
  info: "bg-[var(--info)]",
  muted: "bg-[var(--muted-fg)]",
};

function formatNumber(n: number): string {
  if (Number.isInteger(n)) return n.toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function pct(b: ProgressBar): number {
  const cur = b.current ?? 0;
  return b.target > 0 ? (cur / b.target) * 100 : 0;
}

export function ProgressModule({
  data,
  config,
}: {
  data: ProgressData;
  config: ProgressConfig;
}) {
  const showValues = config.show_values ?? true;
  const showPercent = config.show_percent ?? true;
  const density = config.density ?? "normal";
  const sort = config.sort ?? "as-is";
  const bars = data.bars ?? [];

  if (bars.length === 0) {
    const msg = config.empty_message;
    return (
      <p className="text-sm text-[var(--muted-fg)] italic">
        {msg || "No progress bars."}
      </p>
    );
  }

  const ordered = [...bars];
  switch (sort) {
    case "percent-asc":
      ordered.sort((a, b) => pct(a) - pct(b));
      break;
    case "percent-desc":
      ordered.sort((a, b) => pct(b) - pct(a));
      break;
    case "label":
      ordered.sort((a, b) =>
        String(a.label).localeCompare(String(b.label), undefined, { sensitivity: "base" }),
      );
      break;
    case "as-is":
    default:
      break;
  }

  const rowGap = density === "compact" ? "gap-1.5" : "gap-3";

  return (
    <ul className={cn("flex flex-col", rowGap)}>
      {ordered.map((b, i) => {
        const p = pct(b);
        const fillW = Math.max(0, Math.min(100, p));
        const cur = b.current ?? 0;
        const fillClass = b.severity
          ? SEVERITY_FILL[b.severity]
          : "bg-[var(--module-accent)]";
        const unitStr = b.unit ? ` ${b.unit}` : "";
        return (
          <li
            key={b.id ?? `${b.label}-${i}`}
            title={b.hint ?? undefined}
            className="flex flex-col gap-1"
          >
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium truncate">{b.label}</span>
              {showValues && (
                <span className="tabular-nums text-[var(--muted-fg)] shrink-0">
                  {formatNumber(cur)}
                  {" / "}
                  {formatNumber(b.target)}
                  {unitStr}
                  {showPercent && (
                    <span className="ml-1.5 font-medium text-[var(--fg)]">
                      ({p.toFixed(0)}%)
                    </span>
                  )}
                </span>
              )}
            </div>
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-[var(--muted)]"
              role="progressbar"
              aria-valuenow={Number.isFinite(p) ? Math.round(p) : undefined}
              aria-valuemin={0}
            >
              <div
                className={cn("h-full rounded-full transition-[width]", fillClass)}
                style={{ width: `${fillW}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
