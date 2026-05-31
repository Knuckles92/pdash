"use client";

import { AlertTriangle } from "lucide-react";

import type { IframeAllowlistEntry, Module } from "@/lib/api";

import { ActionButtonModule } from "./ActionButtonModule";
import { FileModule } from "./FileModule";
import { IframeModule } from "./IframeModule";
import { KeyValueModule } from "./KeyValueModule";
import { LinkListModule } from "./LinkListModule";
import { LogStreamModule } from "./LogStreamModule";
import { MarkdownModule } from "./MarkdownModule";
import { NotificationModule } from "./NotificationModule";
import { TableModule } from "./TableModule";
import { TimeseriesModule } from "./TimeseriesModule";

export function ModuleRenderer({
  module: m,
  iframeAllowlist,
  preview = false,
}: {
  module: Module;
  iframeAllowlist?: IframeAllowlistEntry[];
  preview?: boolean;
}) {
  try {
    switch (m.type) {
      case "markdown":
        return <MarkdownModule data={m.data as never} config={m.config as never} />;
      case "key_value":
        return <KeyValueModule data={m.data as never} config={m.config as never} />;
      case "table":
        return <TableModule data={m.data as never} config={m.config as never} />;
      case "link_list":
        return <LinkListModule data={m.data as never} config={m.config as never} />;
      case "timeseries":
        return <TimeseriesModule data={m.data as never} config={m.config as never} />;
      case "log_stream":
        return (
          <LogStreamModule
            data={m.data as never}
            config={m.config as never}
            moduleId={m.id}
            preview={preview}
          />
        );
      case "iframe":
        return (
          <IframeModule
            data={m.data as never}
            config={m.config as never}
            allowlist={iframeAllowlist}
          />
        );
      case "notification":
        return (
          <NotificationModule
            moduleId={m.id}
            data={m.data as never}
            config={m.config as never}
          />
        );
      case "action_button":
        return (
          <ActionButtonModule
            moduleId={m.id}
            data={m.data as never}
            config={m.config as never}
          />
        );
      case "file":
        return <FileModule data={m.data as never} config={m.config as never} />;
      default:
        return (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
            <AlertTriangle className="size-4 mt-0.5 text-amber-600" />
            <div>
              <p className="font-medium">Unsupported module type: {m.type}</p>
              <p className="text-xs text-[var(--muted-fg)]">
                Lands in a later phase.
              </p>
            </div>
          </div>
        );
    }
  } catch (err) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm">
        <AlertTriangle className="size-4 mt-0.5 text-red-600" />
        <div>
          <p className="font-medium">Failed to render module.</p>
          <p className="text-xs text-[var(--muted-fg)]">
            {err instanceof Error ? err.message : "Unknown error"}
          </p>
        </div>
      </div>
    );
  }
}
