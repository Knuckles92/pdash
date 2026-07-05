"use client";

import { Frame, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { api, errorMessage, type IframeAllowlistEntry } from "@/lib/api";

// Accepts: foo.example.com, *.example.com, single-label localhost-ish names.
// Rejects: protocols, slashes, spaces.
const HOST_RE = /^(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/;

type Props = { initialEntries: IframeAllowlistEntry[] };

export function IframeAllowlistClient({ initialEntries }: Props) {
  const [entries, setEntries] = useState(initialEntries);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [host, setHost] = useState("");
  const [pathPrefix, setPathPrefix] = useState("");
  const [desc, setDesc] = useState("");
  const [entryToRemove, setEntryToRemove] = useState<IframeAllowlistEntry | null>(null);
  const [removing, setRemoving] = useState(false);

  function resetForm() {
    setHost("");
    setPathPrefix("");
    setDesc("");
  }

  async function handleAdd() {
    const trimmed = host.trim().toLowerCase();
    if (!HOST_RE.test(trimmed)) {
      toast.error(
        "Host pattern should look like `example.com` or `*.example.com` (no scheme, no path).",
      );
      return;
    }
    setSubmitting(true);
    try {
      const created = await api.addIframeAllowlist({
        host_pattern: trimmed,
        path_prefix: pathPrefix.trim() || undefined,
        description: desc.trim() || undefined,
      });
      setEntries((curr) => [...curr, created]);
      toast.success("Host allowlisted");
      setCreating(false);
      resetForm();
    } catch (err) {
      toast.error(errorMessage(err, "Add failed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmRemove() {
    if (!entryToRemove) return;
    setRemoving(true);
    try {
      await api.removeIframeAllowlist(entryToRemove.id);
      setEntries((curr) => curr.filter((e) => e.id !== entryToRemove.id));
      toast.success("Removed");
      setEntryToRemove(null);
    } catch (err) {
      toast.error(errorMessage(err, "Remove failed"));
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            Iframe allowlist
          </h2>
          <p className="text-xs text-[var(--muted-fg)]">
            Agents may only reference iframe `src` values whose host matches an entry here.
          </p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="size-4" /> Add host
        </Button>
      </div>
      {entries.length === 0 ? (
        <EmptyState
          icon={<Frame className="size-12" />}
          title="No iframes allowed"
          hint="Add a host (e.g. status.example.com) before agents can embed it. The allowlist is the security boundary."
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Add host
            </Button>
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--border)] bg-[var(--muted)]/60 text-xs font-medium uppercase tracking-wide text-[var(--muted-fg)]">
                <tr>
                  <th className="text-left px-4 py-2">Host pattern</th>
                  <th className="text-left px-4 py-2 hidden md:table-cell">
                    Path prefix
                  </th>
                  <th className="text-left px-4 py-2 hidden md:table-cell">
                    Description
                  </th>
                  <th className="text-right px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {entries.map((e) => (
                  <tr key={e.id} className="transition-colors hover:bg-[var(--muted)]/60">
                    <td className="px-4 py-2 font-mono">{e.host_pattern}</td>
                    <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)] font-mono">
                      {e.path_prefix ?? "—"}
                    </td>
                    <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                      {e.description ?? ""}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setEntryToRemove(e)}
                        aria-label="Remove"
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
      )}

      <ConfirmDialog
        open={entryToRemove !== null}
        onClose={() => setEntryToRemove(null)}
        title="Remove from allowlist?"
        description={
          entryToRemove
            ? `Remove "${entryToRemove.host_pattern}" from the iframe allowlist? Modules referencing it will stop rendering.`
            : undefined
        }
        confirmLabel="Remove"
        loadingLabel="Removing"
        icon={<Trash2 className="size-4" />}
        loading={removing}
        onConfirm={confirmRemove}
      />

      <Dialog
        open={creating}
        onClose={() => {
          if (!submitting) setCreating(false);
        }}
        title="Allowlist iframe host"
        description="Hosts can be exact (foo.example.com) or wildcard-prefix (*.example.com)."
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setCreating(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button onClick={handleAdd} disabled={submitting || !host.trim()}>
              {submitting ? "Adding…" : "Add"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label>Host pattern</Label>
            <Input
              autoFocus
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="e.g. grafana.lan or *.example.com"
            />
            <p className="text-xs text-[var(--muted-fg)]">
              Prefer host-only entries. Wildcard subdomains are accepted but
              risky if a subdomain ever falls to a different operator.
            </p>
          </div>
          <div className="flex flex-col gap-1">
            <Label>Path prefix (optional)</Label>
            <Input
              value={pathPrefix}
              onChange={(e) => setPathPrefix(e.target.value)}
              placeholder="/dashboards"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label>Description (optional)</Label>
            <Input
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="What this host is for"
            />
          </div>
        </div>
      </Dialog>
    </div>
  );
}
