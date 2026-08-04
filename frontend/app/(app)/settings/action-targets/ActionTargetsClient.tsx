"use client";

import { Pencil, Play, Plug, Plus, Power, PowerOff, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
  type ActionTarget,
  type ActionTargetDraft,
  type ActionTargetKind,
  type ActionTargetMode,
  type Agent,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { upsertById } from "@/lib/collections";

const KIND_TABS: { kind: ActionTargetKind; label: string; blurb: string }[] = [
  {
    kind: "webhook",
    label: "Webhooks",
    blurb: "Outbound HTTP request to a URL with method, headers, body.",
  },
  {
    kind: "local_script",
    label: "Local scripts",
    blurb: "Run a command on this host. Args/env/timeout configurable.",
  },
  {
    kind: "mcp_tool",
    label: "MCP tools",
    blurb: "Call a tool on a remote MCP server (e.g. Home Assistant).",
  },
  {
    kind: "agent_message",
    label: "Agent messages",
    blurb: "Drop a row in agent_messages for a target agent.",
  },
];

const REDACTED = "***REDACTED***";

// Default config skeleton per kind shown in the form.
const DEFAULT_CONFIG: Record<ActionTargetKind, Record<string, unknown>> = {
  webhook: { url: "", method: "POST", headers: {}, timeout_seconds: 30 },
  local_script: { command: "", timeout_seconds: 30 },
  mcp_tool: { url: "", tool_name: "", auth: null, timeout_seconds: 30 },
  agent_message: { to_agent_id: "" },
};

type FormState = {
  name: string;
  kind: ActionTargetKind;
  mode: ActionTargetMode;
  enabled: boolean;
  configRaw: string;
  // mcp_tool secret entry helper
  bearerSecret: string;
};

function newFormForKind(kind: ActionTargetKind): FormState {
  return {
    name: "",
    kind,
    mode: "sync",
    enabled: true,
    configRaw: JSON.stringify(DEFAULT_CONFIG[kind], null, 2),
    bearerSecret: "",
  };
}

/** Read the selected target agent id out of a raw agent_message config blob. */
function readToAgentId(configRaw: string): string {
  try {
    return (JSON.parse(configRaw) as { to_agent_id?: string }).to_agent_id ?? "";
  } catch {
    return "";
  }
}

export function ActionTargetsClient({
  initialTargets,
}: {
  initialTargets: ActionTarget[];
}) {
  const [targets, setTargets] = useState(initialTargets);
  const [activeKind, setActiveKind] = useState<ActionTargetKind>("webhook");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<ActionTarget | null>(null);
  const [form, setForm] = useState<FormState>(() => newFormForKind("webhook"));
  const [submitting, setSubmitting] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [targetToDelete, setTargetToDelete] = useState<ActionTarget | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Lazy-load agents for the agent_message kind.
  useEffect(() => {
    if (activeKind !== "agent_message" && form.kind !== "agent_message") return;
    api
      .listAgents()
      .then((res) => setAgents(res.items.filter((a) => a.status === "active")))
      .catch(() => setAgents([]));
  }, [activeKind, form.kind]);

  const filtered = useMemo(
    () => targets.filter((t) => t.kind === activeKind),
    [targets, activeKind],
  );

  function openCreate(kind: ActionTargetKind) {
    setEditing(null);
    setForm(newFormForKind(kind));
    setCreating(true);
  }

  function openEdit(t: ActionTarget) {
    setEditing(t);
    setForm({
      name: t.name,
      kind: t.kind,
      mode: t.mode,
      enabled: t.enabled,
      configRaw: JSON.stringify(t.config, null, 2),
      bearerSecret: "",
    });
    setCreating(true);
  }

  function upsertLocal(t: ActionTarget) {
    setTargets((curr) => upsertById(curr, t));
  }

  function parseConfig(): Record<string, unknown> | null {
    try {
      const parsed = JSON.parse(form.configRaw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        toast.error("Config must be a JSON object.");
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch (err) {
      toast.error("Config is not valid JSON: " + errorMessage(err, "parse error"));
      return null;
    }
  }

  function stripRedactedFromConfig(
    cfg: Record<string, unknown>,
  ): Record<string, unknown> {
    // Walk and drop any value equal to *** so we don't accidentally overwrite
    // the server's existing value with the placeholder string.
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(cfg)) {
      if (typeof v === "string" && v === REDACTED) continue;
      if (v && typeof v === "object" && !Array.isArray(v)) {
        out[k] = stripRedactedFromConfig(v as Record<string, unknown>);
      } else {
        out[k] = v;
      }
    }
    return out;
  }

  function notifyBearerSecretMustBeStoredManually(target_id: string) {
    // This does NOT persist the secret. For mcp_tool kind with a bearer secret
    // typed in: store under kv_settings via PATCH /action-targets/{id} extra
    // route? No — we don't expose that. The convention is documented and an
    // admin sets the secret out-of-band via the CLI tool. For Phase 4 UX we
    // accept it in the form but note it must also be stored separately via
    // /scripts/set-secret.sh.
    if (!form.bearerSecret) return;
    toast.info(
      "Bearer secret captured in form but not persisted — store it in kv_settings under " +
        `action_target_secret:${target_id}:main`,
    );
  }

  async function handleSave() {
    const cfg = parseConfig();
    if (cfg === null) return;
    if (!form.name.trim()) {
      toast.error("Name is required.");
      return;
    }
    setSubmitting(true);
    try {
      let saved: ActionTarget;
      const cleanCfg = stripRedactedFromConfig(cfg);
      if (editing) {
        saved = await api.patchActionTarget(editing.id, {
          name: form.name.trim(),
          config: cleanCfg,
          mode: form.mode,
          enabled: form.enabled,
        });
      } else {
        const draft: ActionTargetDraft = {
          name: form.name.trim(),
          kind: form.kind,
          config: cleanCfg,
          mode: form.mode,
          enabled: form.enabled,
        };
        saved = await api.createActionTarget(draft);
      }
      upsertLocal(saved);
      if (form.kind === "mcp_tool" && form.bearerSecret) {
        notifyBearerSecretMustBeStoredManually(saved.id);
      }
      toast.success(editing ? "Target updated" : "Target created");
      setCreating(false);
    } catch (err) {
      toast.error(errorMessage(err, "Save failed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function setTargetEnabled(t: ActionTarget, enable: boolean) {
    try {
      const next = await api.patchActionTarget(t.id, { enabled: enable });
      upsertLocal(next);
      toast.success(enable ? "Enabled" : "Disabled");
    } catch (err) {
      toast.error(errorMessage(err, "Failed"));
    }
  }

  async function confirmDeleteTarget() {
    if (!targetToDelete) return;
    setDeleting(true);
    try {
      await api.deleteActionTarget(targetToDelete.id);
      setTargets((curr) => curr.filter((x) => x.id !== targetToDelete.id));
      toast.success("Deleted");
      setTargetToDelete(null);
    } catch (err) {
      toast.error(errorMessage(err, "Delete failed"));
    } finally {
      setDeleting(false);
    }
  }

  async function testTarget(t: ActionTarget) {
    try {
      const res = await api.testActionTarget(t.id);
      toast[res.ok ? "success" : "error"](res.message);
    } catch (err) {
      toast.error(errorMessage(err, "Test failed"));
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            Action targets
          </h2>
          <p className="text-xs text-[var(--muted-fg)]">
            Action buttons resolve their work via these targets. Secrets are
            stored in kv_settings (not in the config blob).
          </p>
        </div>
        <Button size="sm" onClick={() => openCreate(activeKind)}>
          <Plus className="size-4" /> New {KIND_TABS.find((k) => k.kind === activeKind)?.label.toLowerCase().replace(/s$/, "")}
        </Button>
      </div>

      <nav className="flex gap-1 overflow-x-auto border-b border-[var(--border)]">
        {KIND_TABS.map((tab) => (
          <button
            key={tab.kind}
            type="button"
            onClick={() => setActiveKind(tab.kind)}
            className={cn(
              "shrink-0 whitespace-nowrap px-3 py-2 text-sm border-b-2 -mb-px transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
              activeKind === tab.kind
                ? "border-[var(--accent)] font-medium text-[var(--accent)]"
                : "border-transparent text-[var(--muted-fg)] hover:border-[var(--border-strong)] hover:text-[var(--fg)]",
            )}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <p className="text-xs text-[var(--muted-fg)]">
        {KIND_TABS.find((t) => t.kind === activeKind)?.blurb}
      </p>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Plug className="size-12" />}
          title={`No ${KIND_TABS.find((t) => t.kind === activeKind)?.label.toLowerCase()} configured`}
          hint="Action targets are reusable webhook/script/MCP endpoints that action_button modules fire."
          action={
            <Button onClick={() => openCreate(activeKind)}>
              <Plus className="size-4" /> Add target
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
                  <th className="text-left px-4 py-2 hidden md:table-cell">
                    Mode
                  </th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-right px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {filtered.map((t) => (
                  <tr key={t.id} className="transition-colors hover:bg-[var(--muted)]/60">
                    <td className="px-4 py-2 font-medium">{t.name}</td>
                    <td className="px-4 py-2 hidden md:table-cell">
                      <Badge tone="neutral">{t.mode}</Badge>
                    </td>
                    <td className="px-4 py-2">
                      <Badge tone={t.enabled ? "success" : "neutral"}>
                        {t.enabled ? "enabled" : "disabled"}
                      </Badge>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => testTarget(t)}
                          title="Test"
                          aria-label="Test"
                        >
                          <Play className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => openEdit(t)}
                          title="Edit"
                          aria-label="Edit"
                        >
                          <Pencil className="size-4" />
                        </Button>
                        {t.enabled ? (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setTargetEnabled(t, false)}
                            aria-label="Disable"
                            title="Disable"
                          >
                            <PowerOff className="size-4" />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setTargetEnabled(t, true)}
                            aria-label="Enable"
                            title="Enable"
                          >
                            <Power className="size-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setTargetToDelete(t)}
                          aria-label="Delete"
                          title="Delete"
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

      <ConfirmDialog
        open={targetToDelete !== null}
        onClose={() => setTargetToDelete(null)}
        title="Delete action target?"
        description={
          targetToDelete ? `Delete target "${targetToDelete.name}"?` : undefined
        }
        confirmLabel="Delete target"
        loadingLabel="Deleting"
        icon={<Trash2 className="size-4" />}
        loading={deleting}
        onConfirm={confirmDeleteTarget}
      />

      <Dialog
        open={creating}
        onClose={() => {
          if (!submitting) setCreating(false);
        }}
        title={editing ? `Edit target: ${editing.name}` : `New ${form.kind} target`}
        description={
          editing
            ? "Secrets in the config show as *** and only update when you change them."
            : "Pick a name and fill in the kind-specific config."
        }
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setCreating(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={submitting}>
              {submitting ? "Saving…" : editing ? "Save changes" : "Create"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label>Name</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. ha-bedroom-lights"
              autoFocus
            />
          </div>
          <div className="flex items-center gap-4">
            <div className="flex flex-col gap-1">
              <Label>Mode</Label>
              <select
                value={form.mode}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    mode: e.target.value as ActionTargetMode,
                  }))
                }
                className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-2 py-1.5 text-sm shadow-[var(--shadow-xs)] transition-[border-color,box-shadow] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]"
              >
                <option value="sync">sync</option>
                <option value="async">async</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm mt-6">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) =>
                  setForm((f) => ({ ...f, enabled: e.target.checked }))
                }
                className="size-4"
              />
              <span>Enabled</span>
            </label>
          </div>
          {form.kind === "agent_message" && (
            <div className="flex flex-col gap-1">
              <Label>Target agent</Label>
              <select
                className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm shadow-[var(--shadow-xs)] transition-[border-color,box-shadow] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]"
                value={readToAgentId(form.configRaw)}
                onChange={(e) => {
                  const next = { ...DEFAULT_CONFIG.agent_message, to_agent_id: e.target.value };
                  setForm((f) => ({
                    ...f,
                    configRaw: JSON.stringify(next, null, 2),
                  }));
                }}
              >
                <option value="">— select agent —</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.display_name}
                  </option>
                ))}
              </select>
            </div>
          )}
          {form.kind === "mcp_tool" && !editing && (
            <div className="flex flex-col gap-1">
              <Label>Bearer secret (optional)</Label>
              <Input
                type="password"
                value={form.bearerSecret}
                onChange={(e) =>
                  setForm((f) => ({ ...f, bearerSecret: e.target.value }))
                }
                placeholder="If your MCP server needs an Authorization: Bearer …"
              />
              <p className="text-xs text-[var(--muted-fg)]">
                The secret is shown once. Store it in kv_settings under
                {" "}
                <code className="font-mono">action_target_secret:&lt;id&gt;:main</code>
                {" "}
                after saving (CLI bootstrap).
              </p>
            </div>
          )}
          <div className="flex flex-col gap-1">
            <Label>Config JSON</Label>
            <textarea
              value={form.configRaw}
              onChange={(e) =>
                setForm((f) => ({ ...f, configRaw: e.target.value }))
              }
              rows={10}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs font-mono shadow-[var(--shadow-xs)] transition-[border-color,box-shadow] hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]"
              spellCheck={false}
            />
          </div>
        </div>
      </Dialog>
    </div>
  );
}
