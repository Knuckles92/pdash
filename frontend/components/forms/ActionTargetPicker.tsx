"use client";

import { useEffect, useState } from "react";

import { Label } from "@/components/ui/Label";
import { api, type ActionTarget } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * Custom widget for `action_target_id` fields. Loads the list of available
 * action targets on mount and renders a select. Used in `action_button` and
 * `notification` module forms.
 */
export function ActionTargetPicker({
  value,
  onChange,
  label,
  required,
}: {
  value: unknown;
  onChange: (v: unknown) => void;
  label?: string;
  required?: boolean;
}) {
  const [targets, setTargets] = useState<ActionTarget[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .listActionTargets()
      .then((res) => {
        if (cancelled) return;
        setTargets(res.items.filter((t) => !t.deleted_at && t.enabled));
      })
      .catch(() => setTargets([]))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const current = typeof value === "string" ? value : "";

  return (
    <div className="flex flex-col gap-1">
      {label && (
        <Label>
          {label}
          {required && <span className="text-[var(--danger)]"> *</span>}
        </Label>
      )}
      <select
        className={cn(
          "block h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm shadow-[var(--shadow-xs)] transition-[border-color,box-shadow]",
          "hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]",
        )}
        value={current}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{loading ? "Loading…" : "— select target —"}</option>
        {targets.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name} ({t.kind})
          </option>
        ))}
      </select>
      {!loading && targets.length === 0 && (
        <p className="text-xs text-[var(--muted-fg)]">
          No action targets registered. Add one in Settings → Action targets.
        </p>
      )}
    </div>
  );
}
