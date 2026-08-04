"use client";

import { AlertTriangle, Download, FileText } from "lucide-react";
import { useState } from "react";

import { humanizeBytes } from "@/lib/bytes";
import { cn } from "@/lib/cn";
import type { FileConfig, FileData } from "@/lib/modules/types";

export function FileModule({
  data,
  config,
}: {
  data: FileData;
  config: FileConfig;
}) {
  const [failed, setFailed] = useState(false);
  const rawUrl = `/api/v1/files/${data.file_id}/raw`;
  const downloadUrl = `/api/v1/files/${data.file_id}/download`;
  const showName = config.show_filename ?? true;
  const showDownload = config.show_download ?? true;
  const size = humanizeBytes(data.size_bytes);

  if (failed) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-[var(--warning)]/25 bg-[var(--warning-soft)] p-3 text-sm">
        <AlertTriangle className="size-4 mt-0.5 text-[var(--warning)]" />
        <div className="min-w-0">
          <p className="font-medium">File unavailable.</p>
          <p className="text-xs text-[var(--muted-fg)] truncate">{data.display_name}</p>
        </div>
      </div>
    );
  }

  if (data.kind === "image") {
    return (
      <div className="flex flex-col gap-1.5">
        {/* eslint-disable-next-line @next/next/no-img-element -- same-origin /api file, not a static asset */}
        <img
          src={rawUrl}
          alt={data.alt ?? data.display_name}
          onError={() => setFailed(true)}
          style={{ maxHeight: config.max_height_px ?? 480 }}
          className={cn(
            "w-full rounded-lg border border-[var(--border)] bg-[var(--card)]",
            config.fit === "cover" ? "object-cover" : "object-contain",
          )}
        />
        {showName && (
          <div className="flex items-center justify-between gap-2 text-xs text-[var(--muted-fg)]">
            <span className="truncate" title={data.display_name}>
              {data.display_name}
            </span>
            {showDownload && (
              <a
                href={downloadUrl}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 transition-colors hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                aria-label="Download file"
              >
                <Download className="size-3" />
              </a>
            )}
          </div>
        )}
      </div>
    );
  }

  // document — a download card.
  return (
    <a
      href={downloadUrl}
      className="flex items-center gap-3 rounded-lg border border-[var(--border)] p-3 transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--muted)]/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
    >
      <FileText className="size-8 text-[var(--muted-fg)] shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{data.display_name}</p>
        <p className="truncate text-xs text-[var(--muted-fg)]">
          {[data.mime, size].filter(Boolean).join(" · ") || "Download"}
        </p>
      </div>
      {showDownload && <Download className="size-4 text-[var(--muted-fg)] shrink-0" />}
    </a>
  );
}
