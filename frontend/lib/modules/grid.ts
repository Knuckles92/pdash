/**
 * Per-module grid layout helpers. A module's `grid` JSON blob carries an
 * optional `colspan` (1 | 2 | 3) controlling how many dashboard columns the
 * widget occupies: 1 = normal, 2 = wide, 3 = full row.
 *
 * The dashboard grid is `grid-cols-1 lg:grid-cols-2 xl:grid-cols-3`, so the
 * span only matters from `lg` up. Tailwind v4 only emits classes it sees as
 * literal strings, so the span classes MUST stay spelled out in this map — a
 * computed `col-span-${n}` would never be generated.
 */

export type Colspan = 1 | 2 | 3;

const SPAN_CLASS: Record<Colspan, string> = {
  1: "", // 1 column at every breakpoint
  2: "lg:col-span-2 xl:col-span-2", // full width at lg, 2/3 at xl
  3: "lg:col-span-2 xl:col-span-3", // full width at every breakpoint
};

/** Read `grid.colspan`, coercing anything unexpected (old/garbage data) to 1. */
export function colspanOf(grid: Record<string, unknown> | null | undefined): Colspan {
  const v = grid?.colspan;
  return v === 2 || v === 3 ? v : 1;
}

/** Tailwind class string for an explicit span value (used for live previews). */
export function colspanClassFor(span: Colspan): string {
  return SPAN_CLASS[span];
}

/** Tailwind class string for a module's column span, for the grid child. */
export function colspanClass(grid: Record<string, unknown> | null | undefined): string {
  return SPAN_CLASS[colspanOf(grid)];
}
