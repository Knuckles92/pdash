"use client";

import { Check, ListPlus, Palette, Pencil, Pin, Plus, Trash2, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { NoteContent, NotePin, noteFontFamily } from "@/components/modules/StickyNoteModule";
import { api, errorMessage, type Module } from "@/lib/api";
import { cn } from "@/lib/cn";
import { NOTE_COLOR_ORDER, noteSwatch, type NotesTheme } from "@/lib/modules/corkboard";
import type {
  ChecklistItem,
  NoteColor,
  StickyNoteConfig,
  StickyNoteData,
} from "@/lib/modules/types";
import { relativeTime } from "@/lib/time";

function autosize(el: HTMLTextAreaElement) {
  el.style.height = "0px";
  el.style.height = `${el.scrollHeight}px`;
}

/**
 * One interactive note on a corkboard board. The board owns layout, ordering and
 * which note is being edited; this component owns content editing (title, markdown
 * body, checklist), color, pin-to-top, done and delete — all admin-path, optimistic
 * and immediate. Its look comes entirely from the active `theme`.
 */
export function StickyNote({
  module: m,
  theme,
  editing,
  onStartEdit,
  onStopEdit,
  onUpdated,
  onDeleted,
}: {
  module: Module;
  theme: NotesTheme;
  editing: boolean;
  onStartEdit: () => void;
  onStopEdit: () => void;
  onUpdated: (m: Module) => void;
  onDeleted: (id: string) => void;
}) {
  const data = m.data as StickyNoteData;
  const config = m.config as StickyNoteConfig;
  const color: NoteColor = config.color ?? "yellow";
  const fontFamily = theme.allowHandFont ? noteFontFamily(config.font) : undefined;
  const visual = theme.note(color);

  const [draftTitle, setDraftTitle] = useState(data.title ?? "");
  const [draftText, setDraftText] = useState(data.text ?? "");
  const [draftItems, setDraftItems] = useState<ChecklistItem[]>(data.items ?? []);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const titleRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const itemRefs = useRef<(HTMLInputElement | null)[]>([]);
  const cancelRef = useRef(false);
  const prevEditing = useRef(editing);
  // Monotonic write counter — only the newest in-flight PATCH may apply its
  // server response, so an earlier (now-stale) response can't clobber a later
  // optimistic change.
  const seqRef = useRef(0);

  // Refs holding the latest values so the edit-exit flush reads fresh data even
  // when it runs from an effect (closure values would be stale).
  const dataRef = useRef(data);
  dataRef.current = data;
  const mRef = useRef(m);
  mRef.current = m;
  const draftTitleRef = useRef(draftTitle);
  draftTitleRef.current = draftTitle;
  const draftTextRef = useRef(draftText);
  draftTextRef.current = draftText;
  const draftItemsRef = useRef(draftItems);
  draftItemsRef.current = draftItems;

  // While not editing, keep drafts in sync with the server value.
  useEffect(() => {
    if (editing) return;
    setDraftTitle(data.title ?? "");
    setDraftText(data.text ?? "");
    setDraftItems(data.items ?? []);
  }, [data.title, data.text, data.items, editing]);

  useLayoutEffect(() => {
    if (!editing) return;
    const ta = textRef.current;
    if (ta) autosize(ta);
  }, [editing, draftText]);

  useEffect(() => {
    if (!editing) return;
    const ta = textRef.current;
    ta?.focus();
    ta?.setSelectionRange(ta.value.length, ta.value.length);
  }, [editing]);

  async function persist(
    patch: Parameters<typeof api.patchModule>[1],
    optimistic: Module,
  ) {
    const prev = mRef.current;
    const mySeq = ++seqRef.current;
    onUpdated(optimistic);
    try {
      const server = await api.patchModule(prev.id, patch);
      if (seqRef.current === mySeq) onUpdated(server);
    } catch (err) {
      if (seqRef.current === mySeq) onUpdated(prev);
      toast.error(errorMessage(err, "Save failed"));
    }
  }

  /** Merge a partial onto the freshest data and persist it. */
  function saveData(partial: Partial<StickyNoteData>) {
    const next = { ...dataRef.current, ...partial };
    void persist({ data: next }, { ...mRef.current, data: next });
  }

  /** Persist buffered title + body + checklist together on edit exit. */
  function flush() {
    const d = dataRef.current;
    const nextTitle = draftTitleRef.current.trim().slice(0, 200);
    const nextText = draftTextRef.current.replace(/\s+$/, "");
    const nextItems = draftItemsRef.current.map((it) => ({
      text: it.text.slice(0, 500),
      done: it.done,
    }));
    const unchanged =
      nextTitle === (d.title ?? "") &&
      nextText === (d.text ?? "") &&
      JSON.stringify(nextItems) === JSON.stringify(d.items ?? []);
    if (unchanged) return;
    const next = { ...d, title: nextTitle, text: nextText, items: nextItems };
    void persist({ data: next }, { ...mRef.current, data: next });
  }

  // Persist any title/body edits when edit mode ends (covers Done, click-away,
  // and the board switching to another note). Escape sets cancelRef to skip it.
  useEffect(() => {
    const was = prevEditing.current;
    prevEditing.current = editing;
    if (was && !editing) {
      if (cancelRef.current) cancelRef.current = false;
      else flush();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  function setColor(c: NoteColor) {
    setPaletteOpen(false);
    if (c === color) return;
    const cfg = { ...config, color: c };
    void persist({ config: cfg }, { ...m, config: cfg });
  }

  // In edit mode, checklist changes are buffered into draftItems and persisted by
  // flush() on edit exit (so Escape is a true cancel and there's a single write).
  // In read mode the only checklist interaction is toggling a box — persist it now.
  function toggleItem(i: number) {
    if (editing) {
      setDraftItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, done: !it.done } : it)));
      return;
    }
    const next = (dataRef.current.items ?? []).map((it, idx) =>
      idx === i ? { ...it, done: !it.done } : it,
    );
    setDraftItems(next);
    saveData({ items: next });
  }

  function setItemText(i: number, text: string) {
    setDraftItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, text } : it)));
  }

  function addItem() {
    const focusIdx = draftItemsRef.current.length;
    if (!editing) onStartEdit();
    setDraftItems((prev) => [...prev, { text: "", done: false }]);
    requestAnimationFrame(() => itemRefs.current[focusIdx]?.focus());
  }

  function removeItem(i: number) {
    setDraftItems((prev) => prev.filter((_, idx) => idx !== i));
  }

  function togglePin() {
    saveData({ pinned: !dataRef.current.pinned });
  }
  function toggleDone() {
    saveData({ done: !dataRef.current.done });
  }

  async function remove() {
    onDeleted(m.id);
    try {
      await api.deleteModule(m.id);
      toast.success("Note removed");
    } catch (err) {
      onUpdated(m);
      toast.error(errorMessage(err, "Delete failed"));
    }
  }

  function escapeEdit() {
    cancelRef.current = true;
    setDraftTitle(data.title ?? "");
    setDraftText(data.text ?? "");
    setDraftItems(data.items ?? []);
    onStopEdit();
  }

  function handleCardBlur(e: React.FocusEvent<HTMLDivElement>) {
    if (!editing) return;
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    onStopEdit();
  }

  return (
    <div
      onBlur={handleCardBlur}
      onDoubleClick={(e) => {
        if (editing) return;
        if ((e.target as HTMLElement).closest("[data-no-drag]")) return;
        onStartEdit();
      }}
      className={cn("group relative", visual.className, editing && "ring-2 ring-[var(--accent)]/45")}
      style={{ ...visual.style, zIndex: editing ? 20 : undefined }}
    >
      {visual.showPin && <NotePin pinStyle={config.pin_style ?? "pin"} />}
      {visual.accent.kind === "strip" && (
        <span
          aria-hidden
          className="absolute inset-x-3 top-0 h-1.5 rounded-b-full"
          style={{ background: visual.accent.color }}
        />
      )}
      {visual.accent.kind === "bar" && (
        <span
          aria-hidden
          className="absolute inset-y-2.5 left-0 w-1 rounded-r-full"
          style={{ background: visual.accent.color }}
        />
      )}
      {data.pinned && (
        <span
          aria-hidden
          title="Pinned"
          className="absolute -right-1.5 -top-1.5 z-10 grid size-5 place-items-center rounded-full bg-[var(--accent)] text-[var(--accent-fg)] shadow"
        >
          <Pin className="size-3" />
        </span>
      )}

      {visual.ruled && (
        <span
          aria-hidden
          className="absolute inset-y-3 left-[14px] w-px"
          style={{ background: "#eeb4b4" }}
        />
      )}

      <div className="relative flex flex-col gap-2">
        {visual.accent.kind === "dot" && (
          <span aria-hidden className="size-2.5 rounded-full" style={{ background: visual.accent.color }} />
        )}

        {editing ? (
          <>
            <input
              ref={titleRef}
              data-no-drag
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  textRef.current?.focus();
                } else if (e.key === "Escape") {
                  escapeEdit();
                }
              }}
              placeholder="Title"
              className="w-full bg-transparent text-[15px] font-semibold leading-snug outline-none placeholder:opacity-40"
              style={{ color: "inherit", fontFamily }}
            />
            <textarea
              ref={textRef}
              data-no-drag
              rows={1}
              value={draftText}
              onChange={(e) => {
                setDraftText(e.target.value);
                autosize(e.target);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") escapeEdit();
                else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onStopEdit();
              }}
              placeholder="Take a note…  (markdown supported)"
              className="w-full resize-none overflow-hidden bg-transparent text-[14px] leading-snug outline-none placeholder:opacity-40"
              style={{ color: "inherit", fontFamily }}
            />
            {draftItems.length > 0 && (
              <ul className="flex flex-col gap-1">
                {draftItems.map((it, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <button
                      type="button"
                      data-no-drag
                      onClick={() => toggleItem(i)}
                      role="checkbox"
                      aria-checked={it.done}
                      aria-label={it.text.trim() ? `Toggle: ${it.text}` : "Toggle checklist item"}
                      className={cn(
                        "grid size-[15px] shrink-0 place-items-center rounded-[4px] border",
                        it.done ? "border-current bg-current/10" : "border-current/45",
                      )}
                    >
                      {it.done && <Check className="size-3" strokeWidth={3} aria-hidden />}
                    </button>
                    <input
                      ref={(el) => {
                        itemRefs.current[i] = el;
                      }}
                      data-no-drag
                      value={it.text}
                      onChange={(e) => setItemText(i, e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          setDraftItems((prev) => [
                            ...prev.slice(0, i + 1),
                            { text: "", done: false },
                            ...prev.slice(i + 1),
                          ]);
                          requestAnimationFrame(() => itemRefs.current[i + 1]?.focus());
                        } else if (e.key === "Backspace" && it.text === "") {
                          e.preventDefault();
                          removeItem(i);
                          requestAnimationFrame(() =>
                            itemRefs.current[Math.max(0, i - 1)]?.focus(),
                          );
                        } else if (e.key === "Escape") {
                          escapeEdit();
                        }
                      }}
                      placeholder="List item"
                      className={cn(
                        "min-w-0 flex-1 bg-transparent text-[14px] leading-snug outline-none placeholder:opacity-40",
                        it.done && "line-through opacity-55",
                      )}
                      style={{ color: "inherit", fontFamily }}
                    />
                    <button
                      type="button"
                      data-no-drag
                      onClick={() => removeItem(i)}
                      aria-label="Remove item"
                      className="opacity-50 transition-opacity hover:opacity-100"
                    >
                      <X className="size-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              data-no-drag
              onClick={addItem}
              className="flex items-center gap-1 self-start text-[12px] opacity-60 transition-opacity hover:opacity-100"
            >
              <Plus className="size-3.5" /> Add item
            </button>
          </>
        ) : (
          <NoteContent
            data={data}
            onToggleItem={toggleItem}
            fontFamily={fontFamily}
            emptyHint="Double-click to write…"
          />
        )}

        <div className="mt-1 flex items-center justify-between text-[10px] opacity-50">
          <span>{m.owner_kind === "agent" ? "from agent" : "you"}</span>
          <span>{relativeTime(m.updated_at)}</span>
        </div>
      </div>

      {/* Hover / focus toolbar */}
      <div
        data-no-drag
        className="absolute -bottom-3.5 left-1/2 z-10 flex -translate-x-1/2 items-center gap-0.5 rounded-full border px-1.5 py-1 opacity-0 shadow-[var(--shadow-md)] backdrop-blur-sm transition-opacity focus-within:opacity-100 group-hover:opacity-100"
        style={{ backgroundColor: "color-mix(in srgb, var(--card) 97%, transparent)", borderColor: "var(--border)" }}
      >
        {!editing && (
          <ToolbarButton title="Edit" onClick={onStartEdit}>
            <Pencil className="size-3.5" />
          </ToolbarButton>
        )}
        <ToolbarButton title="Add checklist item" onClick={addItem}>
          <ListPlus className="size-3.5" />
        </ToolbarButton>
        <ToolbarButton
          title={data.pinned ? "Unpin" : "Pin to top"}
          onClick={togglePin}
          active={data.pinned}
        >
          <Pin className="size-3.5" />
        </ToolbarButton>
        <ToolbarButton
          title={data.done ? "Mark not done" : "Mark done"}
          onClick={toggleDone}
          active={data.done}
          activeClass="text-[var(--success)]"
        >
          <Check className="size-3.5" />
        </ToolbarButton>
        <div className="relative">
          <ToolbarButton title="Change color" onClick={() => setPaletteOpen((v) => !v)}>
            <Palette className="size-3.5" />
          </ToolbarButton>
          {paletteOpen && (
            <div
              className="absolute bottom-8 left-1/2 z-20 flex -translate-x-1/2 gap-1 rounded-lg border bg-[var(--card)] p-1.5 shadow-[var(--shadow-md)]"
              style={{ borderColor: "var(--border)" }}
            >
              {NOTE_COLOR_ORDER.map((c) => (
                <button
                  key={c}
                  type="button"
                  data-no-drag
                  title={c}
                  onClick={() => setColor(c)}
                  className={cn(
                    "size-5 rounded-full border transition-transform hover:scale-110",
                    c === color ? "border-transparent ring-2 ring-[var(--accent)]" : "border-black/15",
                  )}
                  style={{ backgroundColor: noteSwatch(c) }}
                />
              ))}
            </div>
          )}
        </div>
        <ToolbarButton
          title={confirmDelete ? "Click again to delete" : "Delete note"}
          onClick={() => {
            if (confirmDelete) void remove();
            else {
              setConfirmDelete(true);
              setTimeout(() => setConfirmDelete(false), 2500);
            }
          }}
          active={confirmDelete}
          activeClass="text-[var(--danger)]"
        >
          <Trash2 className="size-3.5" />
        </ToolbarButton>
      </div>
    </div>
  );
}

function ToolbarButton({
  title,
  onClick,
  active,
  activeClass,
  children,
}: {
  title: string;
  onClick: () => void;
  active?: boolean;
  activeClass?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      data-no-drag
      title={title}
      onClick={onClick}
      className={cn(
        "grid size-6 place-items-center rounded-full text-[var(--muted-fg)] transition-colors hover:bg-[var(--fg)]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
        active && (activeClass ?? "text-[var(--accent)]"),
      )}
    >
      {children}
    </button>
  );
}
