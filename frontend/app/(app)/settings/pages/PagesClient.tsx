"use client";

import { Eraser, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { api, errorMessage, type Page } from "@/lib/api";
import { upsertById } from "@/lib/collections";

type Props = { initialPages: Page[]; initialHomeExampleCount: number };

type PendingConfirm =
  | { kind: "delete-page"; page: Page }
  | { kind: "clear-examples" }
  | { kind: "deploy-examples" };

export function PagesClient({ initialPages, initialHomeExampleCount }: Props) {
  const [pages, setPages] = useState(initialPages);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Page | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [homeExampleCount, setHomeExampleCount] = useState(initialHomeExampleCount);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const router = useRouter();

  const homePage = pages.find((p) => p.type === "home");

  function upsertLocal(p: Page) {
    setPages((curr) => upsertById(curr, p));
  }

  async function handleConfirmAction() {
    if (!pendingConfirm) return;
    setConfirmBusy(true);
    try {
      if (pendingConfirm.kind === "delete-page") {
        const p = pendingConfirm.page;
        if (p.type === "home") {
          toast.error("Cannot delete the home page.");
          return;
        }
        await api.deletePage(p.id);
        setPages((curr) => curr.filter((x) => x.id !== p.id));
        toast.success("Page deleted");
        router.refresh();
      } else if (pendingConfirm.kind === "clear-examples") {
        if (!homePage) return;
        const { cleared } = await api.clearHomeExamples(homePage.id);
        setHomeExampleCount(0);
        toast.success(
          `Cleared ${cleared} default ${cleared === 1 ? "example module" : "example modules"}`,
        );
        router.refresh();
      } else {
        if (!homePage) return;
        const { deployed } = await api.deployHomeExamples(homePage.id);
        setHomeExampleCount(deployed);
        toast.success(`Restored ${deployed} example ${deployed === 1 ? "module" : "modules"}`);
        router.refresh();
      }
      setPendingConfirm(null);
    } catch (err) {
      toast.error(errorMessage(err, "Action failed"));
    } finally {
      setConfirmBusy(false);
    }
  }

  const exampleLabel = homeExampleCount === 1 ? "example module" : "example modules";
  const confirmDialogProps =
    pendingConfirm?.kind === "delete-page"
      ? {
          title: "Delete page?",
          description: `"${pendingConfirm.page.name}" and its modules will be soft-deleted.`,
          confirmLabel: "Delete page",
          loadingLabel: "Deleting",
          icon: <Trash2 className="size-4" />,
          children: (
            <p className="text-sm text-[var(--muted-fg)]">
              This soft-deletes the page and cascades to its modules.
            </p>
          ),
        }
      : pendingConfirm?.kind === "clear-examples"
        ? {
            title: "Clear example modules?",
            description: `Remove ${homeExampleCount} default ${exampleLabel} from Home?`,
            confirmLabel: "Clear examples",
            loadingLabel: "Clearing",
            confirmVariant: "primary" as const,
            children: (
              <p className="text-sm text-[var(--muted-fg)]">
                Only the seeded demo modules are removed. Your other modules stay put.
              </p>
            ),
          }
        : pendingConfirm?.kind === "deploy-examples"
          ? {
              title: "Restore example modules?",
              description: "Deploy 9 example modules to Home?",
              confirmLabel: "Restore examples",
              loadingLabel: "Restoring",
              confirmVariant: "primary" as const,
              children: (
                <p className="text-sm text-[var(--muted-fg)]">
                  Adds the default demo modules back to the home page.
                </p>
              ),
            }
          : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight">Pages</h2>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="size-4" /> New page
        </Button>
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-[var(--border)] bg-[var(--muted)]/60 text-xs font-medium uppercase tracking-wide text-[var(--muted-fg)]">
              <tr>
                <th className="text-left px-4 py-2">Name</th>
                <th className="text-left px-4 py-2">Slug</th>
                <th className="text-left px-4 py-2 hidden md:table-cell">Description</th>
                <th className="text-left px-4 py-2">Type</th>
                <th className="text-right px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {pages.map((p) => (
                <tr key={p.id} className="transition-colors hover:bg-[var(--muted)]/60">
                  <td className="px-4 py-2 font-medium">{p.name}</td>
                  <td className="px-4 py-2 font-mono text-xs">{p.slug}</td>
                  <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                    {p.description ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={p.type === "home" ? "info" : "neutral"}>{p.type}</Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {p.type === "home" && homeExampleCount > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPendingConfirm({ kind: "clear-examples" })}
                          aria-label="Clear examples"
                          title="Clear examples"
                          disabled={confirmBusy}
                        >
                          <Eraser className="size-4" />
                          <span className="hidden sm:inline">
                            {confirmBusy ? "Clearing" : "Clear examples"}
                          </span>
                        </Button>
                      )}
                      {p.type === "home" && homeExampleCount === 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPendingConfirm({ kind: "deploy-examples" })}
                          aria-label="Restore examples"
                          title="Restore examples"
                          disabled={confirmBusy}
                        >
                          <Sparkles className="size-4" />
                          <span className="hidden sm:inline">
                            {confirmBusy ? "Restoring" : "Restore examples"}
                          </span>
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setEditing(p)}
                        aria-label="Edit"
                        title="Edit"
                      >
                        <Pencil className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setPendingConfirm({ kind: "delete-page", page: p })}
                        aria-label="Delete"
                        title={p.type === "home" ? "Cannot delete home" : "Delete"}
                        disabled={p.type === "home"}
                      >
                        <Trash2 className="size-4 text-[var(--danger)]" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {confirmDialogProps && (
        <ConfirmDialog
          open={pendingConfirm !== null}
          onClose={() => setPendingConfirm(null)}
          loading={confirmBusy}
          onConfirm={handleConfirmAction}
          {...confirmDialogProps}
        />
      )}
      <CreatePageDialog
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(p) => {
          upsertLocal(p);
          router.refresh();
        }}
        submitting={submitting}
        setSubmitting={setSubmitting}
      />
      {editing && (
        <EditPageDialog
          page={editing}
          onClose={() => setEditing(null)}
          onSaved={(p) => {
            upsertLocal(p);
            setEditing(null);
            router.refresh();
          }}
          submitting={submitting}
          setSubmitting={setSubmitting}
        />
      )}
    </div>
  );
}

function CreatePageDialog({
  open,
  onClose,
  onSaved,
  submitting,
  setSubmitting,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (p: Page) => void;
  submitting: boolean;
  setSubmitting: (b: boolean) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [type, setType] = useState("custom");
  const [description, setDescription] = useState("");

  async function handleSave() {
    setSubmitting(true);
    try {
      const p = await api.createPage({
        name: name.trim(),
        slug: slug.trim(),
        type,
        description: description.trim() || undefined,
      });
      onSaved(p);
      setName("");
      setSlug("");
      setType("custom");
      setDescription("");
      onClose();
      toast.success("Page created");
    } catch (err) {
      toast.error(errorMessage(err, "Create failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New page"
      description="Slug must be lowercase letters, digits, and dashes (1–40 chars)."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={submitting || !name.trim() || !/^[a-z0-9-]{1,40}$/.test(slug)}
          >
            {submitting ? "Creating…" : "Create"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Slug</Label>
          <Input
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
            placeholder="my-dashboard"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Type</Label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="block w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm shadow-[var(--shadow-xs)] transition-[border-color,box-shadow] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]"
          >
            <option value="custom">custom</option>
            <option value="corkboard">corkboard</option>
            <option value="canvas">canvas</option>
            <option value="agent">agent</option>
            <option value="system">system</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label>Description</Label>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
          />
        </div>
      </div>
    </Dialog>
  );
}

function EditPageDialog({
  page,
  onClose,
  onSaved,
  submitting,
  setSubmitting,
}: {
  page: Page;
  onClose: () => void;
  onSaved: (p: Page) => void;
  submitting: boolean;
  setSubmitting: (b: boolean) => void;
}) {
  const [name, setName] = useState(page.name);
  const [slug, setSlug] = useState(page.slug);
  const [description, setDescription] = useState(page.description ?? "");

  async function handleSave() {
    setSubmitting(true);
    try {
      const p = await api.updatePage(page.id, {
        name: name.trim(),
        slug: slug.trim(),
        description: description.trim() || undefined,
      });
      onSaved(p);
      toast.success("Page updated");
    } catch (err) {
      toast.error(errorMessage(err, "Save failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="Edit page"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={submitting || !name.trim() || !/^[a-z0-9-]{1,40}$/.test(slug)}
          >
            {submitting ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Slug</Label>
          <Input
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
            disabled={page.type === "home"}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Description</Label>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
          />
        </div>
      </div>
    </Dialog>
  );
}
