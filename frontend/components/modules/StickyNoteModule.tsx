"use client";

import type { CSSProperties, ReactNode } from "react";
import { Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";
import { NOTE_ACCENT } from "@/lib/modules/corkboard";
import type {
  ChecklistItem,
  NoteColor,
  NoteFont,
  PinStyle,
  StickyNoteConfig,
  StickyNoteData,
} from "@/lib/modules/types";

const HAND_FONT = "'Bradley Hand', 'Segoe Print', 'Comic Sans MS', cursive";

/** Font for note text. Sans is the legible default; "hand" is an explicit opt-in. */
export function noteFontFamily(font: NoteFont | undefined): string | undefined {
  return font === "hand" ? HAND_FONT : undefined;
}

/** The push-pin / tape that fastens a note to the board (Corkboard theme). */
export function NotePin({ pinStyle }: { pinStyle: PinStyle }) {
  if (pinStyle === "none") return null;
  if (pinStyle === "tape") {
    return (
      <div aria-hidden className="pointer-events-none -mb-1 flex justify-center pb-1">
        <span
          className="h-5 w-16 -rotate-3 rounded-[2px] border border-white/40"
          style={{
            background: "linear-gradient(180deg, rgba(255,255,255,0.55), rgba(255,255,255,0.30))",
            boxShadow: "0 1px 2px rgba(0,0,0,0.18)",
          }}
        />
      </div>
    );
  }
  return (
    <div aria-hidden className="pointer-events-none -mb-1 flex justify-center pb-1">
      <span
        className="size-[18px] rounded-full"
        style={{
          background: "radial-gradient(circle at 35% 30%, #ff9a9a 0%, #e0413f 55%, #a11616 100%)",
          boxShadow: "0 3px 4px -1px rgba(0,0,0,0.45), inset 0 -1px 2px rgba(0,0,0,0.35)",
        }}
      />
    </div>
  );
}

/** Compact, sanitized markdown for a note body. Inherits the card's ink color. */
export function NoteMarkdown({ source, style }: { source: string; style?: CSSProperties }) {
  return (
    <div
      className="prose-pdash prose-note break-words text-[14px] leading-snug [&_p]:my-1 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
      style={style}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ node, ...props }) => <a {...props} rel="noopener noreferrer" target="_blank" />,
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}

/** A note's checklist. When `onToggle` is given each row is an interactive checkbox. */
export function NoteChecklist({
  items,
  onToggle,
  className,
}: {
  items: ChecklistItem[];
  onToggle?: (index: number) => void;
  className?: string;
}) {
  if (items.length === 0) return null;
  return (
    <ul className={cn("flex flex-col gap-1", className)}>
      {items.map((item, i) => {
        const box = (
          <span
            className={cn(
              "mt-[3px] grid size-[15px] shrink-0 place-items-center rounded-[4px] border",
              item.done ? "border-current bg-current/10" : "border-current/45",
            )}
          >
            {item.done && <Check className="size-3" strokeWidth={3} aria-hidden />}
          </span>
        );
        const label = (
          <span className={cn("text-[14px] leading-snug", item.done && "line-through opacity-55")}>
            {item.text || <span className="opacity-40">Item</span>}
          </span>
        );
        return (
          <li key={i} className="flex items-start gap-2">
            {onToggle ? (
              <button
                type="button"
                data-no-drag
                onClick={() => onToggle(i)}
                className="flex items-start gap-2 text-left"
                role="checkbox"
                aria-checked={item.done}
                aria-label={item.text?.trim() ? undefined : "Empty checklist item"}
              >
                {box}
                {label}
              </button>
            ) : (
              <span className="flex items-start gap-2">
                {box}
                {label}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Read-only body of a note: title + markdown + checklist, with a graceful empty
 * state. Shared by the read mode of the interactive board card and the static
 * renderer below.
 */
export function NoteContent({
  data,
  emptyHint,
  onToggleItem,
  fontFamily,
}: {
  data: StickyNoteData;
  emptyHint?: ReactNode;
  onToggleItem?: (index: number) => void;
  fontFamily?: string;
}) {
  const title = data.title?.trim() ?? "";
  const text = data.text ?? "";
  const items = data.items ?? [];
  const isEmpty = !title && !text.trim() && items.length === 0;
  const strike = data.done;

  if (isEmpty) {
    return (
      <p className="text-[14px] italic opacity-40" style={{ fontFamily }}>
        {emptyHint ?? "Empty note"}
      </p>
    );
  }

  return (
    <div className={cn("flex flex-col gap-2", strike && "line-through opacity-60")} style={{ fontFamily }}>
      {title && <h3 className="text-[15px] font-semibold leading-snug break-words">{title}</h3>}
      {text.trim() && <NoteMarkdown source={text} />}
      <NoteChecklist items={items} onToggle={onToggleItem} />
    </div>
  );
}

/**
 * Read-only sticky note used by ModuleRenderer outside a corkboard (normal grid
 * cells, approval previews). It renders transparently so it nests cleanly inside
 * the host Card; the note's color shows as a small dot.
 */
export function StickyNoteModule({
  data,
  config,
}: {
  data: StickyNoteData;
  config: StickyNoteConfig;
}) {
  const color: NoteColor = config.color ?? "yellow";
  // Outside a corkboard (normal grid / approval previews) notes always render in
  // the legible app font — the handwriting opt-in is a Corkboard-theme detail.
  return (
    <div className="flex flex-col gap-2 text-[var(--fg)]">
      <span
        aria-hidden
        className="size-2.5 rounded-full"
        style={{ backgroundColor: NOTE_ACCENT[color] }}
      />
      <NoteContent data={data} emptyHint="Empty note" />
    </div>
  );
}
