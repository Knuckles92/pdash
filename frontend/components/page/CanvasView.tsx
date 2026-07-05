"use client";

import { Code2, Pencil } from "lucide-react";

import { HtmlModule } from "@/components/modules/HtmlModule";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import type { Module } from "@/lib/api";
import type { HtmlConfig, HtmlData } from "@/lib/modules/types";

/**
 * View mode for a `canvas` page: the first html module (by position) renders
 * full-bleed in its sandboxed iframe. Other modules are ignored here — they
 * stay reachable through the standard edit mode.
 */
export function CanvasView({
  modules,
  onEnterEdit,
}: {
  /** Position-sorted live modules from PageView. */
  modules: Module[];
  onEnterEdit: () => void;
}) {
  const htmlModule = modules.find((m) => m.type === "html");

  if (!htmlModule) {
    return (
      <EmptyState
        icon={<Code2 className="size-12" />}
        title="This canvas has no HTML module yet"
        hint="A canvas page renders one html module full-bleed. An agent can propose it, or add one in edit mode."
        action={
          <Button onClick={onEnterEdit}>
            <Pencil className="size-4" /> Enter edit mode
          </Button>
        }
      />
    );
  }

  return (
    <div className="h-[calc(100dvh-11rem)] min-h-[480px]">
      <HtmlModule
        data={htmlModule.data as HtmlData}
        config={htmlModule.config as HtmlConfig}
        fill
      />
    </div>
  );
}
