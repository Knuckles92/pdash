"use client";

import { FileText, Files, Image as ImageIcon, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import {
  api,
  errorMessage,
  type FilesOverview,
  type InboxFile,
  type Page,
  type RegisteredFile,
} from "@/lib/api";
import { humanizeBytes } from "@/lib/bytes";
import { refreshOrphanCount } from "@/lib/hooks/useOrphanCount";

type Props = { initialOverview: FilesOverview | null; pages: Page[] };

type PendingConfirm =
  | { kind: "inbox"; file: InboxFile }
  | { kind: "registered"; file: RegisteredFile };

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, "warning" | "accent" | "danger"> = {
    unclaimed: "warning",
    pending_registration: "accent",
    missing: "danger",
  };
  const label = status === "pending_registration" ? "pending" : status;
  return <Badge tone={map[status] ?? "neutral"}>{label}</Badge>;
}

export function FilesClient({ initialOverview, pages }: Props) {
  const [overview, setOverview] = useState(initialOverview);
  const [refreshing, setRefreshing] = useState(false);
  const [assignFile, setAssignFile] = useState<InboxFile | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  const pageLabel = (id: string | null) =>
    id ? (pages.find((p) => p.id === id)?.name ?? id) : "—";

  async function refresh() {
    setRefreshing(true);
    try {
      setOverview(await api.listFiles());
      refreshOrphanCount();
    } catch (err) {
      toast.error(errorMessage(err, "Failed to load files"));
    } finally {
      setRefreshing(false);
    }
  }

  function openAssign(f: InboxFile) {
    setAssignFile(f);
    setDisplayName(f.name);
  }

  async function handleAssign() {
    if (!assignFile) return;
    setSubmitting(true);
    try {
      await api.registerInboxFile({
        name: assignFile.name,
        display_name: displayName.trim() || assignFile.name,
        page_id: assignFile.page_id ?? undefined,
      });
      toast.success("File registered");
      setAssignFile(null);
      await refresh();
    } catch (err) {
      toast.error(errorMessage(err, "Register failed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirmDelete() {
    if (!pendingConfirm) return;
    setConfirmBusy(true);
    try {
      if (pendingConfirm.kind === "inbox") {
        const f = pendingConfirm.file;
        await api.deleteInboxFile({ name: f.name, page_id: f.page_id ?? undefined });
      } else {
        await api.deleteFile(pendingConfirm.file.id);
      }
      toast.success("Deleted");
      setPendingConfirm(null);
      await refresh();
    } catch (err) {
      toast.error(errorMessage(err, "Delete failed"));
    } finally {
      setConfirmBusy(false);
    }
  }

  const inbox = overview?.inbox ?? [];
  const files = overview?.files ?? [];
  const storeOrphans = overview?.store_orphans ?? [];
  const nothing = inbox.length === 0 && files.length === 0 && storeOrphans.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Files</h2>
          <p className="text-xs text-[var(--muted-fg)]">
            Agents drop files into the inbox, then register them. Unclaimed drops and
            files whose bytes vanished show up here for cleanup.
          </p>
        </div>
        <Button size="sm" variant="secondary" onClick={refresh} disabled={refreshing}>
          <RefreshCw className="size-4" /> {refreshing ? "Rescanning…" : "Rescan"}
        </Button>
      </div>

      {overview === null ? (
        <EmptyState
          icon={<Files className="size-12" />}
          title="Couldn't load files"
          hint="The backend may be unreachable. Try Rescan."
          action={<Button onClick={refresh}>Rescan</Button>}
        />
      ) : nothing ? (
        <EmptyState
          icon={<Files className="size-12" />}
          title="No files yet"
          hint="When an agent drops a file into the inbox and registers it, it appears here."
        />
      ) : null}

      {inbox.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
            Inbox ({inbox.length})
          </h3>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--border)] bg-[var(--muted)]/60 text-xs font-medium uppercase tracking-wide text-[var(--muted-fg)]">
                  <tr>
                    <th className="text-left px-4 py-2">Filename</th>
                    <th className="text-left px-4 py-2 hidden md:table-cell">Page</th>
                    <th className="text-left px-4 py-2 hidden md:table-cell">Size</th>
                    <th className="text-left px-4 py-2">Status</th>
                    <th className="text-right px-4 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {inbox.map((f) => (
                    <tr
                      key={`${f.page_id ?? "_"}/${f.name}`}
                      className="transition-colors hover:bg-[var(--muted)]/60"
                    >
                      <td className="px-4 py-2 font-mono flex items-center gap-2">
                        {f.kind === "image" ? (
                          <ImageIcon className="size-4 text-[var(--muted-fg)] shrink-0" />
                        ) : (
                          <FileText className="size-4 text-[var(--muted-fg)] shrink-0" />
                        )}
                        <span className="truncate">{f.name}</span>
                      </td>
                      <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                        {pageLabel(f.page_id)}
                      </td>
                      <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                        {humanizeBytes(f.size_bytes)}
                      </td>
                      <td className="px-4 py-2">
                        <StatusBadge status={f.status} />
                      </td>
                      <td className="px-4 py-2 text-right whitespace-nowrap">
                        {f.status === "unclaimed" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openAssign(f)}
                            aria-label="Register"
                          >
                            <Plus className="size-4" /> Register
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setPendingConfirm({ kind: "inbox", file: f })}
                          aria-label="Delete"
                        >
                          <Trash2 className="size-4 text-[var(--danger)]" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </section>
      )}

      {files.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
            Registered ({files.length})
          </h3>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[var(--border)] bg-[var(--muted)]/60 text-xs font-medium uppercase tracking-wide text-[var(--muted-fg)]">
                  <tr>
                    <th className="text-left px-4 py-2">File</th>
                    <th className="text-left px-4 py-2 hidden md:table-cell">Type</th>
                    <th className="text-left px-4 py-2 hidden md:table-cell">Page</th>
                    <th className="text-left px-4 py-2 hidden md:table-cell">Size</th>
                    <th className="text-right px-4 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {files.map((f) => (
                    <tr key={f.id} className="transition-colors hover:bg-[var(--muted)]/60">
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2 min-w-0">
                          {f.kind === "image" && f.present_on_disk ? (
                            // eslint-disable-next-line @next/next/no-img-element -- same-origin /api file
                            <img
                              src={f.url}
                              alt=""
                              className="size-9 rounded-lg border border-[var(--border)] object-cover shrink-0"
                            />
                          ) : f.kind === "image" ? (
                            <ImageIcon className="size-5 text-[var(--muted-fg)] shrink-0" />
                          ) : (
                            <FileText className="size-5 text-[var(--muted-fg)] shrink-0" />
                          )}
                          <span className="truncate font-medium">{f.display_name}</span>
                          {f.present_on_disk === false && <StatusBadge status="missing" />}
                        </div>
                      </td>
                      <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                        {f.mime}
                      </td>
                      <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                        {pageLabel(f.page_id)}
                      </td>
                      <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                        {humanizeBytes(f.size_bytes)}
                      </td>
                      <td className="px-4 py-2 text-right whitespace-nowrap">
                        <a
                          href={`/api/v1/files/${f.id}/download`}
                          className="inline-flex items-center rounded-lg px-2 py-1 text-xs font-medium transition-colors hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                        >
                          Download
                        </a>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setPendingConfirm({ kind: "registered", file: f })}
                          aria-label="Delete"
                        >
                          <Trash2 className="size-4 text-[var(--danger)]" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </section>
      )}

      {storeOrphans.length > 0 && (
        <p className="text-xs text-[var(--muted-fg)]">
          {storeOrphans.length} orphaned blob{storeOrphans.length === 1 ? "" : "s"} in the
          store with no record (left by a failed registration). These are harmless and can be
          cleaned up on disk.
        </p>
      )}

      <ConfirmDialog
        open={pendingConfirm !== null}
        onClose={() => setPendingConfirm(null)}
        title={
          pendingConfirm?.kind === "inbox" ? "Delete inbox file?" : "Delete registered file?"
        }
        description={
          pendingConfirm?.kind === "inbox"
            ? `Delete "${pendingConfirm.file.name}" from the inbox? This removes the dropped file.`
            : pendingConfirm?.kind === "registered"
              ? `Delete "${pendingConfirm.file.display_name}"? Widgets pointing at it will stop rendering.`
              : undefined
        }
        confirmLabel="Delete file"
        loadingLabel="Deleting"
        icon={<Trash2 className="size-4" />}
        loading={confirmBusy}
        onConfirm={handleConfirmDelete}
      />

      <Dialog
        open={assignFile !== null}
        onClose={() => {
          if (!submitting) setAssignFile(null);
        }}
        title="Register file"
        description="Give the dropped file a display name. It registers on its current page."
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setAssignFile(null)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button onClick={handleAssign} disabled={submitting || !displayName.trim()}>
              {submitting ? "Registering…" : "Register"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label>Display name</Label>
            <Input
              autoFocus
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Shown in the UI"
            />
          </div>
          <p className="text-xs text-[var(--muted-fg)]">
            Page: {pageLabel(assignFile?.page_id ?? null)}
          </p>
        </div>
      </Dialog>
    </div>
  );
}
