"use client";

import type { KeyValueConfig, KeyValueData, KeyValueField } from "@/lib/modules/types";
import { humanizeBytes } from "@/lib/modules/format";
import { severityChipClass } from "@/lib/modules/severity";
import { cn } from "@/lib/cn";

function formatValue(v: KeyValueField["value"], format?: KeyValueConfig["value_format"]): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") {
    if (format === "humanize-number")
      return new Intl.NumberFormat(undefined).format(v);
    if (format === "humanize-bytes") return humanizeBytes(v);
  }
  return String(v);
}

export function KeyValueModule({ data, config }: { data: KeyValueData; config: KeyValueConfig }) {
  const layout = config.layout ?? "two-column";
  const fields = data.fields ?? [];
  const valueClass = config.value_format === "monospace" ? "font-mono" : "";

  if (layout === "inline-chips") {
    return (
      <div className="flex flex-wrap gap-2">
        {fields.map((f, i) => (
          <span
            key={`${f.key}-${i}`}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
              severityChipClass(f.severity),
            )}
          >
            <span className="font-medium">{f.key}</span>
            <span className={cn("opacity-90", valueClass)}>
              {formatValue(f.value, config.value_format)}
              {f.unit ? ` ${f.unit}` : ""}
            </span>
          </span>
        ))}
      </div>
    );
  }

  if (layout === "stacked") {
    return (
      <dl className="flex flex-col gap-3">
        {fields.map((f, i) => (
          <div key={`${f.key}-${i}`} className="flex flex-col gap-0.5">
            <dt className="text-xs uppercase tracking-wide text-[var(--muted-fg)]">{f.key}</dt>
            <dd
              className={cn(
                "inline-flex w-fit items-center gap-1.5 rounded-md border px-2 py-0.5",
                severityChipClass(f.severity),
                valueClass,
              )}
              title={f.hint ?? undefined}
            >
              {formatValue(f.value, config.value_format)}
              {f.unit ? <span className="opacity-70">{f.unit}</span> : null}
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  // two-column
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
      {fields.map((f, i) => (
        <div key={`${f.key}-${i}`} className="contents">
          <dt className="text-[var(--muted-fg)]" title={f.hint ?? undefined}>
            {f.key}
          </dt>
          <dd
            className={cn(
              "inline-flex w-fit items-center gap-1.5 rounded-md border px-2 py-0.5",
              severityChipClass(f.severity),
              valueClass,
            )}
          >
            {formatValue(f.value, config.value_format)}
            {f.unit ? <span className="opacity-70">{f.unit}</span> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}
