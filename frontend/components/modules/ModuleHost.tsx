"use client";

import { GripVertical, Pencil, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import type { Module } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  appearanceCardClass,
  appearanceHeaderClass,
  appearanceVars,
  moduleAppearanceFromConfig,
} from "@/lib/modules/appearance";
import { MODULE_TYPE_LABELS } from "@/lib/modules/labels";
import type { ModuleType } from "@/lib/modules/types";
import { relativeTime } from "@/lib/time";

type Props = {
  module: Module;
  editMode?: boolean;
  onEdit?: (m: Module) => void;
  onDelete?: (m: Module) => void;
  dragHandle?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function ModuleHost({
  module: m,
  editMode = false,
  onEdit,
  onDelete,
  dragHandle,
  children,
  className,
}: Props) {
  const appearance = moduleAppearanceFromConfig(m.config);
  const solidHeader = appearance.theme === "solid";

  // Phase 5: pulse on every updated_at change (after first mount).
  const [pulse, setPulse] = useState(false);
  const firstUpdate = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (firstUpdate.current === undefined) {
      firstUpdate.current = m.updated_at;
      return;
    }
    if (firstUpdate.current !== m.updated_at) {
      firstUpdate.current = m.updated_at;
      setPulse(true);
      const t = setTimeout(() => setPulse(false), 900);
      return () => clearTimeout(t);
    }
  }, [m.updated_at]);

  return (
    <Card
      style={appearanceVars(appearance)}
      className={cn(
        "flex flex-col transition-shadow",
        appearanceCardClass(appearance),
        pulse && "ring-2 ring-[var(--accent)]/40",
        className,
      )}
    >
      <CardHeader
        className={cn(
          "flex-row items-center justify-between gap-2 rounded-t-[11px] py-2.5",
          appearanceHeaderClass(appearance),
          solidHeader && "[&_button]:text-[var(--module-accent-fg)] [&_button:hover]:bg-white/15",
        )}
      >
        <div className="flex items-center gap-2 min-w-0">
          {editMode &&
            (dragHandle ?? (
              <GripVertical
                className={cn(
                  "size-4 cursor-grab",
                  solidHeader ? "text-[var(--module-accent-fg)] opacity-80" : "text-[var(--muted-fg)]",
                )}
              />
            ))}
          <CardTitle className={cn("truncate", solidHeader && "text-[var(--module-accent-fg)]")}>
            {m.title ?? (
              <span className={cn(solidHeader ? "text-[var(--module-accent-fg)] opacity-80" : "text-[var(--muted-fg)]")}>
                Untitled {MODULE_TYPE_LABELS[m.type as ModuleType] ?? m.type}
              </span>
            )}
          </CardTitle>
          <span
            className={cn(
              "font-mono text-[10px] uppercase tracking-[0.1em]",
              solidHeader ? "text-[var(--module-accent-fg)] opacity-80" : "text-[var(--muted-fg)]/80",
            )}
          >
            {MODULE_TYPE_LABELS[m.type as ModuleType] ?? m.type}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span
            className={cn(
              "hidden md:inline font-mono text-[11px] tabular-nums",
              solidHeader ? "text-[var(--module-accent-fg)] opacity-80" : "text-[var(--muted-fg)]",
            )}
          >
            {relativeTime(m.updated_at)}
          </span>
          {editMode && (
            <>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onEdit?.(m)}
                aria-label="Edit module"
                title="Edit"
              >
                <Pencil className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onDelete?.(m)}
                aria-label="Delete module"
                title="Delete"
              >
                <Trash2
                  className={cn(
                    "size-4",
                    solidHeader ? "text-[var(--module-accent-fg)]" : "text-[var(--danger)]",
                  )}
                />
              </Button>
            </>
          )}
        </div>
      </CardHeader>
      <CardBody>{children}</CardBody>
    </Card>
  );
}
