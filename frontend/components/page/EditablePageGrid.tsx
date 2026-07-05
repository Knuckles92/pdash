"use client";

import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Plus, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ModuleHost } from "@/components/modules/ModuleHost";
import { ModuleRenderer } from "@/components/modules/ModuleRenderer";
import { api, errorMessage, type Module } from "@/lib/api";
import { cn } from "@/lib/cn";
import { upsertById } from "@/lib/collections";
import { type Colspan, colspanClassFor, colspanOf } from "@/lib/modules/grid";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

import { AddModuleSheet } from "./AddModuleSheet";

type Props = {
  pageId: string;
  initialModules: Module[];
};

export function EditablePageGrid({ pageId, initialModules }: Props) {
  const [modules, setModules] = useState<Module[]>(initialModules);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editing, setEditing] = useState<Module | null>(null);
  const [moduleToDelete, setModuleToDelete] = useState<Module | null>(null);
  const [deleting, setDeleting] = useState(false);
  const gridRef = useRef<HTMLDivElement | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  async function handleDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const oldIdx = modules.findIndex((m) => m.id === active.id);
    const newIdx = modules.findIndex((m) => m.id === over.id);
    if (oldIdx < 0 || newIdx < 0) return;
    const next = arrayMove(modules, oldIdx, newIdx);
    setModules(next);
    try {
      await api.reorderModules(
        pageId,
        next.map((m) => m.id),
      );
    } catch (err) {
      toast.error(errorMessage(err, "Reorder failed"));
      // rollback
      setModules(modules);
    }
  }

  async function confirmDeleteModule() {
    if (!moduleToDelete) return;
    const m = moduleToDelete;
    const prev = modules;
    setDeleting(true);
    setModules((curr) => curr.filter((x) => x.id !== m.id));
    try {
      await api.deleteModule(m.id);
      toast.success("Module deleted");
      setModuleToDelete(null);
    } catch (err) {
      setModules(prev);
      toast.error(errorMessage(err, "Delete failed"));
    } finally {
      setDeleting(false);
    }
  }

  function handleSaved(saved: Module) {
    setModules((curr) => upsertById(curr, saved));
  }

  async function handleResize(m: Module, colspan: Colspan) {
    if (colspan === colspanOf(m.grid)) return;
    const prev = modules;
    // Merge — `grid` is a generic JSON blob; don't clobber other keys.
    const nextGrid = { ...(m.grid ?? {}), colspan };
    setModules((curr) =>
      curr.map((x) => (x.id === m.id ? { ...x, grid: nextGrid } : x)),
    );
    try {
      const saved = await api.patchModule(m.id, { grid: nextGrid });
      setModules((curr) => curr.map((x) => (x.id === m.id ? saved : x)));
    } catch (err) {
      setModules(prev); // rollback
      toast.error(errorMessage(err, "Resize failed"));
    }
  }

  return (
    <>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={modules.map((m) => m.id)} strategy={rectSortingStrategy}>
          <div ref={gridRef} className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {modules.map((m) => (
              <SortableModule
                key={m.id}
                module={m}
                gridRef={gridRef}
                onEdit={(mod) => {
                  setEditing(mod);
                  setSheetOpen(true);
                }}
                onDelete={setModuleToDelete}
                onResize={handleResize}
              />
            ))}
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setSheetOpen(true);
              }}
              className={cn(
                "flex min-h-32 flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed",
                "border-[var(--border-strong)] text-[var(--muted-fg)] transition-colors",
                "hover:border-[var(--accent-border)] hover:bg-[var(--accent-soft)]/50 hover:text-[var(--accent)]",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
              )}
            >
              <Plus className="size-6" />
              <span className="text-sm font-medium">Add module</span>
            </button>
          </div>
        </SortableContext>
      </DndContext>

      <AddModuleSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        pageId={pageId}
        nextPosition={modules.length}
        module={editing}
        onSaved={handleSaved}
      />

      <ConfirmDialog
        open={moduleToDelete !== null}
        onClose={() => setModuleToDelete(null)}
        title="Delete module?"
        description={
          moduleToDelete
            ? `"${moduleToDelete.title ?? moduleToDelete.type}" will be soft-deleted.`
            : undefined
        }
        confirmLabel="Delete module"
        loadingLabel="Deleting"
        loading={deleting}
        icon={<Trash2 className="size-4" />}
        onConfirm={confirmDeleteModule}
      >
        <p className="text-sm text-[var(--muted-fg)]">
          Deleted modules can be restored within 30 days from the activity log.
        </p>
      </ConfirmDialog>
    </>
  );
}

function SortableModule({
  module: m,
  gridRef,
  onEdit,
  onDelete,
  onResize,
}: {
  module: Module;
  gridRef: React.RefObject<HTMLDivElement | null>;
  onEdit: (m: Module) => void;
  onDelete: (m: Module) => void;
  onResize: (m: Module, colspan: Colspan) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: m.id });

  // Live preview of the span while the resize handle is being dragged.
  const [previewSpan, setPreviewSpan] = useState<Colspan | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const geomRef = useRef<{ cardLeft: number; colW: number; gap: number; numCols: number } | null>(
    null,
  );

  const committedSpan = colspanOf(m.grid);
  const effectiveSpan = previewSpan ?? committedSpan;

  const setRefs = (el: HTMLDivElement | null) => {
    setNodeRef(el);
    cardRef.current = el;
  };

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  function spanFromPointer(clientX: number): Colspan {
    const geo = geomRef.current;
    if (!geo) return committedSpan;
    const raw = Math.round((clientX - geo.cardLeft) / (geo.colW + geo.gap));
    const clamped = Math.min(Math.max(raw, 1), geo.numCols);
    return clamped === 2 || clamped === 3 ? clamped : 1;
  }

  function handleResizeStart(e: React.PointerEvent) {
    if (isDragging) return;
    const grid = gridRef.current;
    const card = cardRef.current;
    if (!grid || !card) return;
    e.stopPropagation(); // keep this gesture off the sortable drag path
    const cs = getComputedStyle(grid);
    const tracks = cs.gridTemplateColumns.split(" ").filter(Boolean);
    const colW = parseFloat(tracks[0] ?? "0");
    const gap = parseFloat(cs.columnGap || "0") || 0;
    geomRef.current = {
      cardLeft: card.getBoundingClientRect().left,
      colW,
      gap,
      numCols: tracks.length,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
    setPreviewSpan(spanFromPointer(e.clientX));
  }

  function handleResizeMove(e: React.PointerEvent) {
    if (!geomRef.current) return;
    setPreviewSpan(spanFromPointer(e.clientX));
  }

  function handleResizeEnd(e: React.PointerEvent) {
    if (!geomRef.current) return;
    geomRef.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* pointer may already be released */
    }
    const next = previewSpan;
    setPreviewSpan(null);
    if (next != null && next !== committedSpan) onResize(m, next);
  }

  return (
    <div ref={setRefs} style={style} className={cn("relative", colspanClassFor(effectiveSpan))}>
      <ModuleHost
        module={m}
        editMode
        onEdit={onEdit}
        onDelete={onDelete}
        dragHandle={
          <button
            type="button"
            className="grid size-6 cursor-grab place-items-center rounded-lg text-[var(--muted-fg)] transition-colors hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] active:cursor-grabbing"
            aria-label="Drag to reorder"
            {...attributes}
            {...listeners}
          >
            <GripVertical className="size-4" />
          </button>
        }
      >
        <ModuleRenderer module={m} />
      </ModuleHost>
      {/* Resize handle — drag to set column span. No-op below lg (1 column). */}
      {!isDragging && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize width"
          onPointerDown={handleResizeStart}
          onPointerMove={handleResizeMove}
          onPointerUp={handleResizeEnd}
          onPointerCancel={handleResizeEnd}
          className={cn(
            "absolute right-0 top-0 z-10 hidden h-full w-2 touch-none cursor-col-resize lg:block",
            "rounded-r-xl transition-colors hover:bg-[var(--accent-soft)]",
          )}
        />
      )}
    </div>
  );
}
