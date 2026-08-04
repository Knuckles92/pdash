"use client";

import { Plus, StickyNote as StickyNoteIcon, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ModuleRenderer } from "@/components/modules/ModuleRenderer";
import { Button } from "@/components/ui/Button";
import { api, errorMessage, type Module } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  DEFAULT_NOTES_THEME,
  NOTES_THEME_IDS,
  NOTES_THEMES,
  NOTE_COLOR_ORDER,
  getNotesTheme,
  loadNotesTheme,
  saveNotesTheme,
  type NotesThemeId,
} from "@/lib/modules/corkboard";
import type { StickyNoteData } from "@/lib/modules/types";

import { StickyNote } from "./StickyNote";

function isPinned(m: Module): boolean {
  return m.type === "sticky_note" && Boolean((m.data as StickyNoteData).pinned);
}

export function CorkboardBoard({ pageId, modules }: { pageId: string; modules: Module[] }) {
  const [notes, setNotes] = useState<Module[]>(modules);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [themeId, setThemeId] = useState<NotesThemeId>(DEFAULT_NOTES_THEME);

  // Load the per-board theme on the client (avoids an SSR hydration mismatch).
  useEffect(() => setThemeId(loadNotesTheme(pageId)), [pageId]);
  const theme = getNotesTheme(themeId);

  // Keep local notes in sync with the server-driven list (SSE refetches in PageView).
  useEffect(() => setNotes(modules), [modules]);

  const updateNote = useCallback(
    (m: Module) => setNotes((prev) => prev.map((n) => (n.id === m.id ? m : n))),
    [],
  );
  const removeNote = useCallback(
    (id: string) => setNotes((prev) => prev.filter((n) => n.id !== id)),
    [],
  );

  // Pinned notes float to the top; otherwise newest first.
  const ordered = useMemo(() => {
    return [...notes].sort((a, b) => {
      const pinDelta = Number(isPinned(b)) - Number(isPinned(a));
      if (pinDelta !== 0) return pinDelta;
      return b.created_at.localeCompare(a.created_at);
    });
  }, [notes]);

  function changeTheme(id: NotesThemeId) {
    setThemeId(id);
    saveNotesTheme(pageId, id);
  }

  async function addNote() {
    setAdding(true);
    const color = NOTE_COLOR_ORDER[notes.length % NOTE_COLOR_ORDER.length];
    try {
      const created = await api.createModule({
        type: "sticky_note",
        page_id: pageId,
        data: { text: "" },
        config: { color },
      });
      setNotes((prev) => [...prev, created]);
      setEditingId(created.id);
    } catch (err) {
      toast.error(errorMessage(err, "Could not add note"));
    } finally {
      setAdding(false);
    }
  }

  const onCork = themeId === "corkboard";
  const onPastel = themeId === "pastel";

  return (
    <div className="flex flex-col gap-3">
      {/* Board toolbar: theme switcher + add */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div
          role="group"
          aria-label="Board theme"
          className="flex flex-wrap items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--card)] p-1 shadow-[var(--shadow-xs)]"
        >
          {NOTES_THEME_IDS.map((id) => {
            const active = id === themeId;
            return (
              <button
                key={id}
                type="button"
                title={NOTES_THEMES[id].blurb}
                aria-pressed={active}
                onClick={() => changeTheme(id)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                  active
                    ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                    : "text-[var(--muted-fg)] hover:bg-[var(--muted)] hover:text-[var(--fg)]",
                )}
              >
                {NOTES_THEMES[id].label}
              </button>
            );
          })}
        </div>
        <Button onClick={addNote} disabled={adding} size="sm">
          <Plus className="size-4" /> Add note
        </Button>
      </div>

      {/* Board frame + surface */}
      <div className={theme.frame.className} style={theme.frame.style}>
        <div
          className={cn("min-h-[52vh]", theme.surface.className)}
          style={theme.surface.style}
        >
          {ordered.length === 0 ? (
            <div className="grid min-h-[44vh] place-items-center">
              <div
                className={cn(
                  "flex flex-col items-center gap-2 text-center",
                  // Pastel paints a fixed light surface, so app's --muted-fg can go
                  // light-on-light in dark mode — pin a readable dark ink instead.
                  onCork ? "text-white/85" : onPastel ? "text-[#6b6357]" : "text-[var(--muted-fg)]",
                )}
              >
                <StickyNoteIcon className={cn("size-10", onCork && "drop-shadow")} />
                <p className={cn("font-medium", onCork && "drop-shadow")}>No notes yet</p>
                <p className={cn("text-sm", onCork ? "text-white/70" : "opacity-80")}>
                  Add your first note, or let an agent leave you one.
                </p>
              </div>
            </div>
          ) : (
            <div className="columns-1 gap-4 sm:columns-2 lg:columns-3 2xl:columns-4">
              {ordered.map((m) => (
                <div key={m.id} className="mb-4 inline-block w-full break-inside-avoid overflow-visible">
                  {m.type === "sticky_note" ? (
                    <StickyNote
                      module={m}
                      theme={theme}
                      editing={editingId === m.id}
                      onStartEdit={() => setEditingId(m.id)}
                      onStopEdit={() => setEditingId((cur) => (cur === m.id ? null : cur))}
                      onUpdated={updateNote}
                      onDeleted={removeNote}
                    />
                  ) : (
                    <FallbackCard module={m} onDeleted={removeNote} />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Non-sticky modules pinned to the board: render read-only with a delete affordance. */
function FallbackCard({ module: m, onDeleted }: { module: Module; onDeleted: (id: string) => void }) {
  async function remove() {
    onDeleted(m.id);
    try {
      await api.deleteModule(m.id);
    } catch (err) {
      toast.error(errorMessage(err, "Delete failed"));
    }
  }
  return (
    <div className="group relative rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 shadow-[var(--shadow-sm)]">
      <ModuleRenderer module={m} />
      <button
        type="button"
        onClick={remove}
        title="Remove from board"
        className="absolute -right-2 -top-2 grid size-6 place-items-center rounded-full border border-[var(--border)] bg-[var(--card)] text-[var(--muted-fg)] opacity-0 shadow-[var(--shadow-sm)] transition-opacity hover:text-[var(--danger)] focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] group-hover:opacity-100"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}
