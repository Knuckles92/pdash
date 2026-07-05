"use client";

import { Copy, KeyRound, Plus, Power, PowerOff, Trash2, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { api, errorMessage, type Agent } from "@/lib/api";
import { cn } from "@/lib/cn";
import { upsertById } from "@/lib/collections";
import { relativeTime } from "@/lib/time";

type Props = { initialAgents: Agent[] };

type PendingConfirm = { kind: "rotate"; agent: Agent } | { kind: "revoke"; agent: Agent };
type AgentStatusFilter = "all" | "active" | "inactive";

const isExampleAgent = (a: Agent) => a.permissions?.pdash_default_example === true;
const isInactiveAgent = (a: Agent) => a.status === "disabled" || a.status === "revoked";

export function AgentsClient({ initialAgents }: Props) {
  const [agents, setAgents] = useState(initialAgents);
  const [statusFilter, setStatusFilter] = useState<AgentStatusFilter>("all");
  const [creating, setCreating] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [newAgentDescription, setNewAgentDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [revealedKey, setRevealedKey] = useState<{ agent: Agent; key: string } | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

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

  async function handleConfirmAction() {
    if (!pendingConfirm) return;
    setConfirmBusy(true);
    try {
      if (pendingConfirm.kind === "rotate") {
        const res = await api.rotateAgentKey(pendingConfirm.agent.id);
        upsertLocal(res.agent);
        setRevealedKey({ agent: res.agent, key: res.api_key });
        toast.success("Key rotated");
      } else {
        const a = pendingConfirm.agent;
        await api.revokeAgent(a.id);
        upsertLocal({ ...a, status: "revoked" });
        toast.success("Agent revoked");
      }
      setPendingConfirm(null);
    } catch (err) {
      toast.error(
        errorMessage(err, pendingConfirm.kind === "rotate" ? "Rotate failed" : "Revoke failed"),
      );
    } finally {
      setConfirmBusy(false);
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

  const activeCount = agents.filter((a) => a.status === "active").length;
  const inactiveCount = agents.filter(isInactiveAgent).length;
  const filteredAgents = agents.filter((a) => {
    if (statusFilter === "active") return a.status === "active";
    if (statusFilter === "inactive") return isInactiveAgent(a);
    return true;
  });
  const statusFilters: { value: AgentStatusFilter; label: string; count: number }[] = [
    { value: "all", label: "All", count: agents.length },
    { value: "active", label: "Active", count: activeCount },
    { value: "inactive", label: "Inactive", count: inactiveCount },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-sm font-semibold tracking-tight">Registered agents</h2>
        <div className="flex flex-wrap items-center gap-2">
          <div
            className="inline-flex h-8 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--card)] shadow-[var(--shadow-xs)]"
            role="group"
            aria-label="Filter agents by status"
          >
            {statusFilters.map((filter) => (
              <button
                key={filter.value}
                type="button"
                onClick={() => setStatusFilter(filter.value)}
                aria-pressed={statusFilter === filter.value}
                className={cn(
                  "inline-flex items-center gap-1 border-r border-[var(--border)] px-3 text-xs font-medium last:border-r-0 transition-colors hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)]",
                  statusFilter === filter.value
                    ? "bg-[var(--accent-soft)] text-[var(--accent)] hover:bg-[var(--accent-soft)]"
                    : "text-[var(--muted-fg)]",
                )}
              >
                <span>{filter.label}</span>
                <span className="tabular-nums opacity-75">{filter.count}</span>
              </button>
            ))}
          </div>
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Register agent
          </Button>
        </div>
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
              <thead className="border-b border-[var(--border)] bg-[var(--muted)]/60 text-xs font-medium uppercase tracking-wide text-[var(--muted-fg)]">
                <tr>
                  <th className="text-left px-4 py-2">Name</th>
                  <th className="text-left px-4 py-2 hidden md:table-cell">Description</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2 hidden md:table-cell">Last rotated</th>
                  <th className="text-right px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {filteredAgents.map((a) => (
                  <tr key={a.id} className="transition-colors hover:bg-[var(--muted)]/60">
                    <td className="px-4 py-2 font-medium">{a.display_name}</td>
                    <td className="px-4 py-2 hidden md:table-cell text-[var(--muted-fg)]">
                      <div className="flex flex-col gap-1">
                        <span>{a.description ?? "—"}</span>
                        {isExampleAgent(a) && (
                          <button
                            type="button"
                            onClick={() => setShowHelp(true)}
                            className="text-left text-xs text-[var(--accent)] hover:underline"
                          >
                            How to register an agent →
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      <Badge
                        tone={
                          a.status === "active"
                            ? "success"
                            : a.status === "revoked"
                              ? "danger"
                              : "neutral"
                        }
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
                          onClick={() => setPendingConfirm({ kind: "rotate", agent: a })}
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
                          onClick={() => setPendingConfirm({ kind: "revoke", agent: a })}
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
                {filteredAgents.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-sm text-[var(--muted-fg)]"
                    >
                      No {statusFilter} agents.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <ConfirmDialog
        open={pendingConfirm !== null}
        onClose={() => setPendingConfirm(null)}
        title={
          pendingConfirm?.kind === "rotate"
            ? "Rotate API key?"
            : pendingConfirm?.kind === "revoke"
              ? "Revoke agent?"
              : ""
        }
        description={
          pendingConfirm?.kind === "rotate"
            ? `Rotate the API key for "${pendingConfirm.agent.display_name}"? The old key stops working immediately.`
            : pendingConfirm?.kind === "revoke"
              ? `Revoke "${pendingConfirm.agent.display_name}"? This cannot be undone.`
              : undefined
        }
        confirmLabel={
          pendingConfirm?.kind === "rotate"
            ? "Rotate key"
            : pendingConfirm?.kind === "revoke"
              ? "Revoke agent"
              : "Confirm"
        }
        loadingLabel={pendingConfirm?.kind === "rotate" ? "Rotating" : "Revoking"}
        confirmVariant={pendingConfirm?.kind === "revoke" ? "danger" : "primary"}
        icon={
          pendingConfirm?.kind === "revoke" ? <Trash2 className="size-4" /> : <KeyRound className="size-4" />
        }
        loading={confirmBusy}
        onConfirm={handleConfirmAction}
      >
        {pendingConfirm?.kind === "rotate" && (
          <p className="text-sm text-[var(--muted-fg)]">
            The new key is shown once after rotation. Update your MCP client config right away.
          </p>
        )}
      </ConfirmDialog>

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
            <div className="flex items-center gap-2 rounded-lg bg-[var(--muted)] py-1 pl-3 pr-1">
              <Input
                readOnly
                value={revealedKey.key}
                className="h-auto min-w-0 flex-1 border-none bg-transparent p-0 font-mono text-xs shadow-none focus-visible:ring-0"
                onFocus={(e) => e.currentTarget.select()}
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Copy API key"
                title="Copy API key"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(revealedKey.key);
                    toast.success("Copied");
                  } catch {
                    toast.error("Clipboard unavailable");
                  }
                }}
              >
                <Copy className="size-4" />
              </Button>
            </div>
            <p className="text-xs text-[var(--muted-fg)]">
              Store this somewhere safe. We only keep an Argon2id hash.
            </p>
          </div>
        )}
      </Dialog>

      <Dialog
        open={showHelp}
        onClose={() => setShowHelp(false)}
        title="How to register an agent"
        description="Mint an API key here, then connect your AI client to the MCP server."
        footer={<Button onClick={() => setShowHelp(false)}>Close</Button>}
      >
        <div className="flex flex-col gap-4 text-sm">
          <div className="flex flex-col gap-2">
            <h4 className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
              Option A — mint a key yourself
            </h4>
            <ol className="flex flex-col gap-2 list-decimal pl-5 marker:text-[var(--muted-fg)]">
              <li>
                Click <span className="font-medium">Register agent</span> at the top-right of this
                page.
              </li>
              <li>
                Enter a display name (e.g. <code className="font-mono text-xs">claude-code</code>)
                and an optional description, then click <span className="font-medium">Register</span>.
              </li>
              <li>
                Copy the API key — it is shown <span className="font-medium">once</span> and stored
                only as an Argon2id hash, so it can never be retrieved again.
              </li>
              <li>
                Add the key to your AI client&apos;s MCP config, pointing it at the MCP server&apos;s{" "}
                <code className="font-mono text-xs">/mcp</code> endpoint.
              </li>
            </ol>
          </div>
          <div className="flex flex-col gap-2">
            <h4 className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
              Option B — let the agent self-register
            </h4>
            <ol className="flex flex-col gap-2 list-decimal pl-5 marker:text-[var(--muted-fg)]">
              <li>
                Have the agent add the MCP <code className="font-mono text-xs">/mcp</code>{" "}
                endpoint to its MCP client config (no key yet) and reload. The{" "}
                <span className="font-medium">MCP</span> tab has a copy-paste prompt that walks
                through setup, <code className="font-mono text-xs">request_registration</code>, and
                adding the key after claim.
              </li>
              <li>
                The request appears in <span className="font-medium">Approvals</span> — approve or
                deny it there.
              </li>
              <li>
                After you approve, the agent picks up its own key by polling{" "}
                <code className="font-mono text-xs">claim_registration</code>, updates its MCP
                config with the key, and reconnects; no key is shown here.
              </li>
            </ol>
          </div>
          <p className="text-xs text-[var(--muted-fg)]">
            Either way the agent authenticates with its key and every write flows through the
            approval engine, appearing in your inbox to approve or deny.
          </p>
        </div>
      </Dialog>
    </div>
  );
}
