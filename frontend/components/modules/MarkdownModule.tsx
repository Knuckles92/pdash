"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/Button";
import type { MarkdownConfig, MarkdownData } from "@/lib/modules/types";
import { severityChipClass } from "@/lib/modules/severity";
import { cn } from "@/lib/cn";

type Props = {
  data: MarkdownData;
  config: MarkdownConfig;
};

export function MarkdownModule({ data, config }: Props) {
  const [collapsed, setCollapsed] = useState<boolean>(!!config.collapsed_by_default);
  const maxHeight = config.max_height_px ?? 600;

  return (
    <div className="flex flex-col gap-2">
      {config.callout_severity && (
        <div
          className={cn(
            "rounded-lg border px-3 py-2 text-xs font-medium",
            severityChipClass(config.callout_severity),
          )}
        >
          {config.callout_severity}
        </div>
      )}
      <div
        className={cn("prose-pdash text-sm")}
        style={{
          maxHeight: collapsed ? 0 : maxHeight,
          overflow: collapsed ? "hidden" : "auto",
          transition: "max-height 200ms",
        }}
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeSanitize]}
          components={{
            a: ({ node, ...props }) => (
              <a {...props} rel="noopener noreferrer" target="_blank" />
            ),
          }}
        >
          {data.body ?? ""}
        </ReactMarkdown>
      </div>
      <div className="flex items-center justify-between text-xs text-[var(--muted-fg)]">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setCollapsed((c) => !c)}
          className="-ml-2"
        >
          {collapsed ? (
            <>
              <ChevronDown className="size-3" /> Expand
            </>
          ) : (
            <>
              <ChevronUp className="size-3" /> Collapse
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
