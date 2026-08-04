"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { paletteHex, tokenToHex } from "@/lib/modules/color_token";
import { humanizeBytes, humanizeDurationMs } from "@/lib/modules/format";
import type {
  TimeseriesConfig,
  TimeseriesData,
  TimeseriesYAxisFormat,
} from "@/lib/modules/types";

function formatValue(v: number | null, fmt?: TimeseriesYAxisFormat, unit?: string | null): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  switch (fmt) {
    case "percent":
      return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(v)}%`;
    case "bytes":
      return humanizeBytes(v);
    case "duration_ms":
      return humanizeDurationMs(v);
    case "auto":
    default:
      return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(v)}${
        unit ? ` ${unit}` : ""
      }`;
  }
}

function formatTooltipTime(t: string | number): string {
  try {
    const d = new Date(t);
    if (Number.isNaN(d.getTime())) return String(t);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return String(t);
  }
}

function formatAxisTime(t: string | number): string {
  try {
    const d = new Date(t);
    if (Number.isNaN(d.getTime())) return String(t);
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  } catch {
    return String(t);
  }
}

type ChartRow = { t: string } & Record<string, number | string | null>;

export function TimeseriesModule({
  data,
  config,
}: {
  data: TimeseriesData;
  config: TimeseriesConfig;
}) {
  const chartType = config.chart_type ?? "line";
  const showLegend = config.show_legend ?? true;
  const fmt = config.y_axis?.format ?? "auto";
  const unit = config.y_axis?.unit ?? null;
  const height = Math.min(
    Math.max(config.height_px ?? 240, 80),
    typeof window !== "undefined" && window.innerWidth < 768 ? 320 : 1200,
  );
  const series = useMemo(() => data.series ?? [], [data.series]);

  // Merge all points across all series on the `t` axis so Recharts can render
  // multi-series. Nulls render as gaps when `connectNulls` is false.
  const { rows, seriesColors } = useMemo(() => {
    const rowsByTimestamp: Record<string, ChartRow> = {};
    series.forEach((s) => {
      (s.points || []).forEach((point) => {
        if (!rowsByTimestamp[point.t]) {
          rowsByTimestamp[point.t] = { t: point.t };
        }
        rowsByTimestamp[point.t]![s.id] = point.v ?? null;
      });
    });
    const rows = Object.values(rowsByTimestamp).sort((a, b) =>
      String(a.t).localeCompare(String(b.t)),
    );
    const seriesColors: Record<string, string> = {};
    series.forEach((s, i) => {
      seriesColors[s.id] = s.color_token ? tokenToHex(s.color_token, i) : paletteHex(i);
    });
    return { rows, seriesColors };
  }, [series]);

  if (rows.length === 0 || series.length === 0) {
    return (
      <p className="text-sm text-[var(--muted-fg)] italic">No data points yet.</p>
    );
  }

  const yMin = config.y_axis?.min ?? "auto";
  const yMax = config.y_axis?.max ?? "auto";

  const Chart = chartType === "bar" ? BarChart : chartType === "area" ? AreaChart : LineChart;

  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <Chart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="t"
            tickFormatter={formatAxisTime}
            stroke="var(--muted-fg)"
            fontSize={11}
            minTickGap={32}
          />
          <YAxis
            stroke="var(--muted-fg)"
            fontSize={11}
            domain={[yMin as never, yMax as never]}
            tickFormatter={(v) => formatValue(v as number, fmt, unit)}
            label={
              config.y_axis?.label
                ? {
                    value: config.y_axis.label,
                    angle: -90,
                    position: "insideLeft",
                    fill: "var(--muted-fg)",
                    fontSize: 11,
                  }
                : undefined
            }
          />
          <Tooltip
            labelFormatter={(t) => formatTooltipTime(t as string)}
            formatter={(value, name) => [
              typeof value === "number"
                ? formatValue(value, fmt, unit)
                : value === null || value === undefined
                  ? "—"
                  : String(value),
              String(name),
            ]}
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              boxShadow: "var(--shadow-md)",
              fontSize: 12,
            }}
          />
          {showLegend && <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted-fg)" }} />}
          {series.map((s) => {
            const color = seriesColors[s.id] ?? paletteHex(0);
            if (chartType === "bar") {
              return <Bar key={s.id} dataKey={s.id} name={s.label} fill={color} />;
            }
            if (chartType === "area") {
              return (
                <Area
                  key={s.id}
                  dataKey={s.id}
                  name={s.label}
                  stroke={color}
                  fill={color}
                  fillOpacity={0.18}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              );
            }
            return (
              <Line
                key={s.id}
                dataKey={s.id}
                name={s.label}
                stroke={color}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
            );
          })}
        </Chart>
      </ResponsiveContainer>
    </div>
  );
}
