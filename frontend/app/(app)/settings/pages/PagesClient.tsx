"use client";

import { Eraser, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { api, errorMessage, type Page } from "@/lib/api";
import { cn } from "@/lib/cn";
import { upsertById } from "@/lib/collections";

type Props = { initialPages: Page[]; initialHomeExampleCount: number };

export function PagesClient({ initialPages, initialHomeExampleCount }: Props) {
  const [pages, setPages] = useState(initialPages);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Page | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [homeExampleCount, setHomeExampleCount] = useState(initialHomeExampleCount);
  const [examplesBusy, setExamplesBusy] = useState(false);
  const router = useRouter();

  const homePage = pages.find((p) => p.kind === "home");

  function upsertLocal(p: Page) {
    setPages((curr) => upsertById(curr, p));
  }

  async function deletePage(p: Page) {
    if (p.kind === "home") {
      toast.error("Cannot delete the home page.");
      return;
    }
    if (!confirm(`Delete page "${p.name}"? This soft-deletes the page and cascades modules.`)) return;
    try {
      await api.deletePage(p.id);
      setPages((curr) => curr.filter((x) => x.id !== p.id));
      toast.success("Page deleted");
      router.refresh();
    } catch (err) {
      toast.error(errorMessage(err, "Delete failed"));
    }
  }

  async function clearDefaultExamples() {
    if (!homePage) return;
    const label = homeExampleCount === 1 ? "example module" : "example modules";
    if (!confirm(`Clear ${homeExampleCount} default ${label} from Home?`)) return;
    setExamplesBusy(true);
    try {
      const { cleared } = await api.clearHomeExamples(homePage.id);
      setHomeExampleCount(0);
      toast.success(`Cleared ${cleared} default ${cleared === 1 ? "example module" : "example modules"}`);
      router.refresh();
    } catch (err) {
      toast.error(errorMessage(err, "Clear examples failed"));
    } finally {
      setExamplesBusy(false);
    }
  }

  async function deployDefaultExamples() {
    if (!homePage) return;
    if (!confirm("Deploy 9 example modules to Home?")) return;
    setExamplesBusy(true);
    try {
      const { deployed } = await api.deployHomeExamples(homePage.id);
      setHomeExampleCount(deployed);
      toast.success(`Restored ${deployed} example ${deployed === 1 ? "module" : "modules"}`);
      router.refresh();
    } catch (err) {
      toast.error(errorMessage(err, "Restore examples failed"));
    } finally {
      setExamplesBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-[var(--muted-fg)]">Pages</h2>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="size-4" /> New page
        </Button>
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-[var(--border)] text-xs uppercase tracking-wide text-[var(--muted-fg)]">
              <tr>
                <th className="text-left px-4 py-2">Name</th>
                <th className="text-left px-4 py-2">Slug</th>
                <th className="text-left px-4 py-2 hidden md:table-cell">Description</th>
                <th className="text-left px-4 py-2">Kind</th>
                <th className="text-right px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pages.map((p) => (
                <tr key={p.id} className="border-b border-[var(--border)] last:border-b-0">
                  <td className="px-4 py-2 font-medium">{p.name}</td>
                  <td className="px-4 py-2 font-mono text-xs">{p.slug}</td>
                  <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                    {p.description ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    <Badge
                      className={cn(
                        p.kind === "home" && "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30",
                      )}
                    >
                      {p.kind}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {p.kind === "home" && homeExampleCount > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => clearDefaultExamples()}
                          aria-label="Clear examples"
                          title="Clear examples"
                          disabled={examplesBusy}
                        >
                          <Eraser className="size-4" />
                          <span className="hidden sm:inline">
                            {examplesBusy ? "Clearing" : "Clear examples"}
                          </span>
                        </Button>
                      )}
                      {p.kind === "home" && homeExampleCount === 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deployDefaultExamples()}
                          aria-label="Restore examples"
                          title="Restore examples"
                          disabled={examplesBusy}
                        >
                          <Sparkles className="size-4" />
                          <span className="hidden sm:inline">
                            {examplesBusy ? "Restoring" : "Restore examples"}
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
                        onClick={() => deletePage(p)}
                        aria-label="Delete"
                        title={p.kind === "home" ? "Cannot delete home" : "Delete"}
                        disabled={p.kind === "home"}
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
  const [kind, setKind] = useState("custom");
  const [description, setDescription] = useState("");

  async function handleSave() {
    setSubmitting(true);
    try {
      const p = await api.createPage({
        name: name.trim(),
        slug: slug.trim(),
        kind,
        description: description.trim() || undefined,
      });
      onSaved(p);
      setName("");
      setSlug("");
      setKind("custom");
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
          <Label>Kind</Label>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="block w-full rounded-md border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm"
          >
            <option value="custom">custom</option>
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
            disabled={page.kind === "home"}
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
