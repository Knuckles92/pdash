"use client";

import { AlertTriangle, ExternalLink } from "lucide-react";
import type React from "react";

import type { IframeAllowlistEntry } from "@/lib/api";
import { cn } from "@/lib/cn";
import { isAllowedIframeSrc } from "@/lib/modules/iframe_allowlist";
import type { IframeConfig, IframeData } from "@/lib/modules/types";

// The agent opts in to scripts/forms/popups/same-origin via config.sandbox;
// an empty string is still fully restrictive (the safe default).
function buildSandbox(flags: string[] | undefined): string {
  return Array.from(new Set(flags ?? [])).join(" ");
}

export function IframeModule({
  data,
  config,
  allowlist,
}: {
  data: IframeData;
  config: IframeConfig;
  /** Server-rendered allowlist from a parent component. Defaults to [] (= refuse). */
  allowlist?: IframeAllowlistEntry[];
}) {
  const src = data.src;
  const heightDesktop = config.height_px ?? 480;
  const heightMobile = config.mobile_height_px ?? 320;
  const showChrome = config.show_chrome ?? true;
  const allowed = allowlist ? isAllowedIframeSrc(src, allowlist) : false;

  if (!allowed) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-[var(--warning)]/25 bg-[var(--warning-soft)] p-3 text-sm">
        <AlertTriangle className="size-4 mt-0.5 text-[var(--warning)]" />
        <div className="min-w-0">
          <p className="font-medium">Iframe blocked: host not allowlisted.</p>
          <p className="text-xs text-[var(--muted-fg)] break-all">
            {src}
          </p>
          <p className="text-xs text-[var(--muted-fg)] mt-1">
            Add this host in Settings → iframe allowlist.
          </p>
        </div>
      </div>
    );
  }

  const sandboxAttr = buildSandbox(config.sandbox);
  return (
    <div className="flex flex-col">
      {showChrome && (
        <div className="flex items-center justify-between border-b border-[var(--border)] px-1 pb-1.5 mb-1 text-xs text-[var(--muted-fg)]">
          <span className="truncate" title={data.title ?? src}>
            {data.title ?? new URL(src).host}
          </span>
          <a
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Open in new tab"
            title="Open in new tab"
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md transition-colors hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            <ExternalLink className="size-3" />
          </a>
        </div>
      )}
      <div
        className="w-full"
        style={
          {
            "--iframe-h-desktop": `${heightDesktop}px`,
            "--iframe-h-mobile": `${heightMobile}px`,
          } as React.CSSProperties
        }
      >
        <iframe
          src={src}
          title={data.title ?? "iframe module"}
          // sandbox="" empty-string is still restrictive, that's the safe default.
          sandbox={sandboxAttr}
          referrerPolicy={config.referrer_policy ?? "strict-origin-when-cross-origin"}
          className={cn(
            // Phase 6: bg-[var(--card)] keeps the iframe surround consistent
            // with the rest of the dashboard in both themes; many embeds
            // render transparent so we want the host card color showing
            // through, not always-white.
            "w-full rounded-lg border border-[var(--border)] bg-[var(--card)]",
            "h-[var(--iframe-h-mobile)] md:h-[var(--iframe-h-desktop)]",
          )}
        />
      </div>
    </div>
  );
}
