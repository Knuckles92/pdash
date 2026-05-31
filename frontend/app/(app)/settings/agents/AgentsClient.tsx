"use client";

import { Copy, KeyRound, Plus, Power, PowerOff, Trash2, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { api, errorMessage, type Agent } from "@/lib/api";
import { cn } from "@/lib/cn";
import { upsertById } from "@/lib/collections";
import { relativeTime } from "@/lib/time";

type Props = { initialAgents: Agent[] };

export function AgentsClient({ initialAgents }: Props) {
  const [agents, setAgents] = useState(initialAgents);
  const [creating, setCreating] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [newAgentDescription, setNewAgentDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [revealedKey, setRevealedKey] = useState<{ agent: Agent; key: string } | null>(null);

  function upsertLocal(agent: Agent) {
    setAgents((curr) => upsertById(curr, agent));
  }

  async function handleCreate() {
    if (!newAgentName.trim()) return;
    setSubmitting(true);
    try {
      const res = await api.createAgent({
        display_name: newAgentName.trim(),
        description: newAgentDescription.trim() || undefined,
      });
      upsertLocal(res.agent);
      setRevealedKey({ agent: res.agent, key: res.api_key });
      setCreating(false);
      setNewAgentName("");
      setNewAgentDescription("");
      toast.success("Agent created");
    } catch (err) {
      toast.error(errorMessage(err, "Create failed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function rotate(a: Agent) {
    if (!confirm(`Rotate the API key for "${a.display_name}"? The old key will stop working immediately.`)) return;
    try {
      const res = await api.rotateAgentKey(a.id);
      upsertLocal(res.agent);
      setRevealedKey({ agent: res.agent, key: res.api_key });
      toast.success("Key rotated");
    } catch (err) {
      toast.error(errorMessage(err, "Rotate failed"));
    }
  }

  async function setEnabled(a: Agent, enable: boolean) {
    try {
      const next = enable ? await api.enableAgent(a.id) : await api.disableAgent(a.id);
      upsertLocal(next);
      toast.success(`Agent ${enable ? "enabled" : "disabled"}`);
    } catch (err) {
      toast.error(errorMessage(err, "Failed"));
    }
  }

  async function revoke(a: Agent) {
    if (!confirm(`Revoke "${a.display_name}"? This cannot be undone.`)) return;
    try {
      await api.revokeAgent(a.id);
      upsertLocal({ ...a, status: "revoked" });
      toast.success("Agent revoked");
    } catch (err) {
      toast.error(errorMessage(err, "Revoke failed"));
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-[var(--muted-fg)]">Registered agents</h2>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="size-4" /> Register agent
        </Button>
      </div>

      {agents.length === 0 ? (
        <EmptyState
          icon={<Users className="size-12" />}
          title="No agents yet"
          hint="Register an agent to mint an API key it can use against the MCP server."
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Register agent
            </Button>
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--border)] text-xs uppercase tracking-wide text-[var(--muted-fg)]">
                <tr>
                  <th className="text-left px-4 py-2">Name</th>
                  <th className="text-left px-4 py-2 hidden md:table-cell">Description</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2 hidden md:table-cell">Last rotated</th>
                  <th className="text-right px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.id} className="border-b border-[var(--border)] last:border-b-0">
                    <td className="px-4 py-2 font-medium">{a.display_name}</td>
                    <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                      {a.description ?? "—"}
                    </td>
                    <td className="px-4 py-2">
                      <Badge
                        className={cn(
                          a.status === "active" && "bg-green-500/15 text-green-700 dark:text-green-300 border-green-500/30",
                          a.status === "disabled" && "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300 border-zinc-500/30",
                          a.status === "revoked" && "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30",
                        )}
                      >
                        {a.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-2 hidden md:table-cell text-xs text-[var(--muted-fg)]">
                      {relativeTime(a.last_key_rotated_at)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => rotate(a)}
                          title="Rotate key"
                          disabled={a.status === "revoked"}
                          aria-label="Rotate key"
                        >
                          <KeyRound className="size-4" />
                        </Button>
                        {a.status === "active" ? (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setEnabled(a, false)}
                            title="Disable"
                            aria-label="Disable"
                          >
                            <PowerOff className="size-4" />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setEnabled(a, true)}
                            disabled={a.status === "revoked"}
                            title="Enable"
                            aria-label="Enable"
                          >
                            <Power className="size-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => revoke(a)}
                          disabled={a.status === "revoked"}
                          title="Revoke"
                          aria-label="Revoke"
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
      )}

      <Dialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Register agent"
        description="The plaintext API key is shown once on creation."
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreating(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={submitting || !newAgentName.trim()}>
              {submitting ? "Creating…" : "Register"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label>Display name</Label>
            <Input
              value={newAgentName}
              onChange={(e) => setNewAgentName(e.target.value)}
              placeholder="e.g. claude-code"
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label>Description</Label>
            <Textarea
              value={newAgentDescription}
              onChange={(e) => setNewAgentDescription(e.target.value)}
              placeholder="Optional"
              rows={3}
            />
          </div>
        </div>
      </Dialog>

      <Dialog
        open={!!revealedKey}
        onClose={() => setRevealedKey(null)}
        title={`API key for ${revealedKey?.agent.display_name ?? ""}`}
        description="This key is only shown once. Copy it now."
        footer={
          <Button onClick={() => setRevealedKey(null)}>I&apos;ve saved it</Button>
        }
      >
        {revealedKey && (
          <div className="flex flex-col gap-3">
            <div className="flex items-stretch gap-2">
              <Input
                readOnly
                value={revealedKey.key}
                className="font-mono text-xs"
                onFocus={(e) => e.currentTarget.select()}
              />
              <Button
                variant="secondary"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(revealedKey.key);
                    toast.success("Copied");
                  } catch {
                    toast.error("Clipboard unavailable");
                  }
                }}
              >
                <Copy className="size-4" /> Copy
              </Button>
            </div>
            <p className="text-xs text-[var(--muted-fg)]">
              Store this somewhere safe. We only keep an Argon2id hash.
            </p>
          </div>
        )}
      </Dialog>
    </div>
  );
}
