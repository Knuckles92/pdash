"use client";

import { useMemo } from "react";

import { ModuleHost } from "@/components/modules/ModuleHost";
import { ModuleRenderer } from "@/components/modules/ModuleRenderer";
import type { IframeAllowlistEntry, Module } from "@/lib/api";
import { colspanClass } from "@/lib/modules/grid";

function pinKey(m: Module): number {
  if (m.type === "notification") {
    const cfg = m.config as { pin_to_top?: boolean } | undefined;
    if (cfg?.pin_to_top) return 0;
  }
  return 1;
}

export function PageGrid({
  modules,
  iframeAllowlist,
}: {
  modules: Module[];
  iframeAllowlist?: IframeAllowlistEntry[];
}) {
  const sorted = useMemo(() => {
    // Stable: pinned notifications first, then existing order preserved.
    return [...modules].sort((a, b) => {
      const k = pinKey(a) - pinKey(b);
      if (k !== 0) return k;
      return 0;
    });
  }, [modules]);
  if (sorted.length === 0) {
    return null;
  }
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
      {sorted.map((m) => (
        <ModuleHost key={m.id} module={m} className={colspanClass(m.grid)}>
          <ModuleRenderer module={m} iframeAllowlist={iframeAllowlist} />
        </ModuleHost>
      ))}
    </div>
  );
}
