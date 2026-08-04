"use client";

import { AlertTriangle } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import {
  APPROVAL_ACTION_TYPES,
  ApiError,
  api,
  type Agent,
  type ApprovalActionType,
  type ApprovalRule,
  type ApprovalRuleDraft,
  type Page,
} from "@/lib/api";
import { isKnownModuleType, MODULE_TYPE_LABELS } from "@/lib/modules/labels";
import { ALL_MODULE_TYPES } from "@/lib/modules/types";

const SELECT_CLASS =
  "h-9 rounded-lg border border-[var(--border-strong)] bg-[var(--bg)] px-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-50";

type RuleEditorMode =
  | { kind: "create"; draft?: Partial<ApprovalRuleDraft> }
  | { kind: "edit"; rule: ApprovalRule };

export type RuleEditorProps = {
  open: boolean;
  onClose: () => void;
  mode: RuleEditorMode;
  agents: Agent[];
  pages?: Page[];
  /** If set, the editor shows the "Apply to N matching pending requests" toggle. */
  pendingMatchCount?: number;
  onSaved?: (rule: ApprovalRule) => void;
};

function ruleToDraft(rule: ApprovalRule): ApprovalRuleDraft {
  return {
    agent_id: rule.agent_id,
    action_type: rule.action_type,
    module_type: rule.module_type,
    module_id: rule.module_id,
    page_id: rule.page_id,
    owner_scope: (rule.owner_scope as "any" | "self" | "other") ?? "any",
    outcome: rule.outcome,
    priority: rule.priority,
    notes: rule.notes ?? null,
    enabled: rule.enabled,
  };
}

const ACTION_LABELS: Record<string, string> = {
  create_module: "Create module",
  update_module_data: "Update module data",
  update_module_config: "Update module settings",
  update_module_meta: "Move or rename module",
  delete_module: "Delete module",
  create_page: "Create page",
  delete_page: "Delete page",
  fire_action_button: "Run action",
  register_agent: "Register agent",
};

const OUTCOME_LABELS: Record<ApprovalRuleDraft["outcome"], string> = {
  auto_approve: "Approve automatically",
  deny: "Deny automatically",
  prompt: "Ask me first",
};

const OWNER_SCOPE_LABELS: Record<NonNullable<ApprovalRuleDraft["owner_scope"]>, string> = {
  any: "Any owner",
  self: "Only targets owned by this agent",
  other: "Only targets not owned by this agent",
};

function emptyDraft(seed?: Partial<ApprovalRuleDraft>): ApprovalRuleDraft {
  return {
    agent_id: seed?.agent_id ?? "",
    action_type: seed?.action_type ?? "update_module_data",
    module_type: seed?.module_type ?? null,
    module_id: seed?.module_id ?? null,
    page_id: seed?.page_id ?? null,
    owner_scope: seed?.owner_scope ?? "any",
    outcome: seed?.outcome ?? "auto_approve",
    priority: seed?.priority ?? 100,
    notes: seed?.notes ?? null,
    enabled: seed?.enabled ?? true,
  };
}

function shortId(id: string): string {
  const [prefix, rest] = id.split("_");
  if (!rest) return id;
  return `${prefix}_${rest.slice(0, 10)}`;
}

function agentLabel(agentId: string | undefined, agents: Agent[]): string {
  if (!agentId) return "an agent you choose";
  if (agentId === "*") return "any agent";
  return agents.find((a) => a.id === agentId)?.display_name ?? shortId(agentId);
}

function pageLabel(pageId: string | null | undefined, pages: Page[]): string | null {
  if (!pageId) return null;
  return pages.find((p) => p.id === pageId)?.name ?? shortId(pageId);
}

export function RuleEditor({
  open,
  onClose,
  mode,
  agents,
  pages = [],
  pendingMatchCount,
  onSaved,
}: RuleEditorProps) {
  const initial = useMemo<ApprovalRuleDraft>(
    () =>
      mode.kind === "edit" ? ruleToDraft(mode.rule) : emptyDraft(mode.draft),
    [mode],
  );
  const [draft, setDraft] = useState<ApprovalRuleDraft>(initial);
  const [applyToPending, setApplyToPending] = useState(false);
  const [confirmingWildcardAgent, setConfirmingWildcardAgent] = useState(false);
  const [wideOpenConfirmOpen, setWideOpenConfirmOpen] = useState(false);
  const [wildcardConfirmOpen, setWildcardConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // We re-init when the dialog is opened with a different mode.
  // (The Dialog returns null when closed, so this state survives only an open
  // session — good enough for our flow.)

  function patch(p: Partial<ApprovalRuleDraft>): void {
    setDraft((d) => ({ ...d, ...p }));
  }

  const isBuiltin = mode.kind === "edit" && mode.rule.is_builtin;

  const hasScope =
    !!draft.module_id ||
    !!draft.page_id ||
    !!draft.module_type ||
    draft.owner_scope !== "any";
  const hasConcreteAgent = !!draft.agent_id && draft.agent_id !== "*";
  const isWideOpen = !hasScope && !hasConcreteAgent;

  async function performSave(): Promise<void> {
    setSubmitting(true);
    try {
      if (mode.kind === "create") {
        const res = await api.createApprovalRule({
          ...draft,
          // Backend treats empty agent_id as invalid; coerce to wildcard.
          agent_id: draft.agent_id || "*",
          apply_to_pending: applyToPending,
        });
        toast.success(
          applyToPending && res.applied_to_pending > 0
            ? `Rule created — applied to ${res.applied_to_pending} pending`
            : "Rule created",
        );
        onSaved?.(res.rule);
      } else {
        const res = await api.patchApprovalRule(mode.rule.id, {
          agent_id: draft.agent_id || "*",
          module_type: draft.module_type ?? null,
          module_id: draft.module_id ?? null,
          page_id: draft.page_id ?? null,
          owner_scope: draft.owner_scope ?? "any",
          outcome: draft.outcome,
          priority: draft.priority ?? 100,
          notes: draft.notes ?? null,
          enabled: draft.enabled ?? true,
        });
        toast.success("Rule updated");
        onSaved?.(res);
      }
      onClose();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Save failed";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSave(): Promise<void> {
    if (!draft.action_type) {
      toast.error("action_type is required");
      return;
    }
    if (isWideOpen) {
      setWideOpenConfirmOpen(true);
      return;
    }
    await performSave();
  }

  const agentOptions = useMemo(
    () => agents.filter((a) => a.status !== "revoked"),
    [agents],
  );
  const pageOptions = useMemo(
    () => pages.filter((p) => !p.deleted_at),
    [pages],
  );
  const pageIdIsKnown = pageOptions.some((p) => p.id === draft.page_id);
  const moduleTypeIsKnown =
    draft.module_type != null && isKnownModuleType(draft.module_type);
  const actionLabel = ACTION_LABELS[draft.action_type] ?? draft.action_type;
  const outcomeLabel = OUTCOME_LABELS[draft.outcome];
  const selectedAgentLabel = agentLabel(draft.agent_id, agentOptions);
  const selectedPageLabel = pageLabel(draft.page_id, pageOptions);
  const moduleTypeLabel =
    draft.module_type && isKnownModuleType(draft.module_type)
      ? MODULE_TYPE_LABELS[draft.module_type]
      : draft.module_type;
  const scopeParts = [
    draft.module_id ? `specific module ${shortId(draft.module_id)}` : null,
    selectedPageLabel ? `page ${selectedPageLabel}` : null,
    moduleTypeLabel ? `${moduleTypeLabel} modules` : null,
    draft.owner_scope && draft.owner_scope !== "any"
      ? OWNER_SCOPE_LABELS[draft.owner_scope]
      : null,
  ].filter(Boolean);
  const scopeSummary = scopeParts.length > 0 ? scopeParts.join(" · ") : "all matching requests";
  const advancedDefaultOpen = mode.kind === "edit" || !mode.draft;
  const dialogTitle = mode.kind === "create" ? "Save as a rule" : "Edit approval rule";

  return (
    <>
    <Dialog
      open={open}
      onClose={onClose}
      title={dialogTitle}
      description={
        isBuiltin
          ? "Built-in safety rule: the match and decision are locked, but you can enable or disable it."
          : "Use this to handle similar future requests without reviewing each one by hand."
      }
      className="max-w-lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={submitting}>
            {submitting ? "Saving…" : "Save rule"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--muted)]/30 p-3">
          <div className="text-[10px] font-medium uppercase tracking-wide text-[var(--muted-fg)]">
            Rule summary
          </div>
          <p className="mt-1 text-sm font-medium text-[var(--fg)]">
            {outcomeLabel} for future {actionLabel.toLowerCase()} requests from{" "}
            {selectedAgentLabel}.
          </p>
          <p className="mt-1 text-xs text-[var(--muted-fg)]">
            Scope: {scopeSummary}.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label>Agent</Label>
            <select
              className={SELECT_CLASS}
              value={draft.agent_id || ""}
              disabled={isBuiltin}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "*" && !confirmingWildcardAgent) {
                  setWildcardConfirmOpen(true);
                  return;
                }
                patch({ agent_id: v });
              }}
            >
              <option value="" disabled>
                Choose an agent…
              </option>
              {agentOptions.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.display_name}
                </option>
              ))}
              <option value="*">Any agent</option>
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <Label>Decision</Label>
            <select
              className={SELECT_CLASS}
              value={draft.outcome}
              disabled={isBuiltin}
              onChange={(e) =>
                patch({ outcome: e.target.value as "auto_approve" | "deny" | "prompt" })
              }
            >
              <option value="auto_approve">{OUTCOME_LABELS.auto_approve}</option>
              <option value="deny">{OUTCOME_LABELS.deny}</option>
              <option value="prompt">{OUTCOME_LABELS.prompt}</option>
            </select>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <Label>Request type</Label>
          <select
            className={SELECT_CLASS}
            value={draft.action_type}
            disabled={isBuiltin || mode.kind === "edit"}
            onChange={(e) =>
              patch({ action_type: e.target.value as ApprovalActionType })
            }
          >
            {APPROVAL_ACTION_TYPES.map((at) => (
              <option key={at} value={at}>
                {ACTION_LABELS[at] ?? at}
              </option>
            ))}
          </select>
        </div>

        <details
          className="rounded-lg border border-[var(--border)] bg-[var(--bg)]"
          open={advancedDefaultOpen}
        >
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
            Scope and advanced settings
          </summary>
          <div className="border-t border-[var(--border)] p-3">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <Label>{pageOptions.length > 0 ? "Page" : "Page ID"}</Label>
                {pageOptions.length > 0 ? (
                  <select
                    className={SELECT_CLASS}
                    value={draft.page_id ?? ""}
                    disabled={isBuiltin}
                    onChange={(e) => patch({ page_id: e.target.value || null })}
                  >
                    <option value="">All pages</option>
                    {pageOptions.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                    {draft.page_id && !pageIdIsKnown && (
                      <option value={draft.page_id}>Unknown page ({draft.page_id})</option>
                    )}
                  </select>
                ) : (
                  <Input
                    placeholder="pg_… (optional)"
                    value={draft.page_id ?? ""}
                    disabled={isBuiltin}
                    onChange={(e) => patch({ page_id: e.target.value || null })}
                  />
                )}
              </div>

              <div className="flex flex-col gap-1">
                <Label>Module type</Label>
                <select
                  className={SELECT_CLASS}
                  value={draft.module_type ?? ""}
                  disabled={isBuiltin}
                  onChange={(e) => patch({ module_type: e.target.value || null })}
                >
                  <option value="">All types</option>
                  {ALL_MODULE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {MODULE_TYPE_LABELS[t]}
                    </option>
                  ))}
                  {draft.module_type && !moduleTypeIsKnown && (
                    <option value={draft.module_type}>
                      Unknown type ({draft.module_type})
                    </option>
                  )}
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <Label>Specific module</Label>
                <Input
                  placeholder="Any module"
                  value={draft.module_id ?? ""}
                  disabled={isBuiltin}
                  onChange={(e) => patch({ module_id: e.target.value || null })}
                />
              </div>

              <div className="flex flex-col gap-1">
                <Label>Ownership</Label>
                <select
                  className={SELECT_CLASS}
                  value={draft.owner_scope ?? "any"}
                  disabled={isBuiltin}
                  onChange={(e) =>
                    patch({ owner_scope: e.target.value as "any" | "self" | "other" })
                  }
                >
                  <option value="any">{OWNER_SCOPE_LABELS.any}</option>
                  <option value="self">{OWNER_SCOPE_LABELS.self}</option>
                  <option value="other">{OWNER_SCOPE_LABELS.other}</option>
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <Label>Priority</Label>
                <Input
                  type="number"
                  value={String(draft.priority ?? 100)}
                  onChange={(e) =>
                    patch({ priority: Number(e.target.value || 100) })
                  }
                />
              </div>
            </div>
          </div>
        </details>

        <div className="flex items-center gap-2">
          <input
            id="rule-enabled"
            type="checkbox"
            className="size-4 accent-[var(--accent)]"
            checked={draft.enabled ?? true}
            onChange={(e) => patch({ enabled: e.target.checked })}
          />
          <Label htmlFor="rule-enabled">Enabled</Label>
        </div>

        {mode.kind === "create" && pendingMatchCount !== undefined && (
          <div className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--muted)]/40 p-2.5">
            <input
              id="apply-pending"
              type="checkbox"
              className="size-4 accent-[var(--accent)]"
              checked={applyToPending}
              onChange={(e) => setApplyToPending(e.target.checked)}
            />
            <Label htmlFor="apply-pending" className="text-xs">
              Also apply this rule to matching requests already waiting ({pendingMatchCount}{" "}
              {pendingMatchCount === 1 ? "match" : "matches"})
            </Label>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <Label>Notes</Label>
          <Textarea
            rows={2}
            className="min-h-20"
            value={draft.notes ?? ""}
            onChange={(e) => patch({ notes: e.target.value || null })}
            placeholder="Optional rationale shown next to the rule"
          />
        </div>

        {isWideOpen && (
          <div className="flex items-start gap-2 rounded-lg border border-[var(--warning)]/25 bg-[var(--warning-soft)] p-3 text-xs text-[var(--warning)]">
            <AlertTriangle className="size-4 shrink-0 mt-0.5" />
            <span>
              Wildcard agent and no scope dimension means this rule fires for{" "}
              <em>every</em> request of action_type{" "}
              <code className="font-mono">{draft.action_type}</code>. You will be
              asked to confirm on save.
            </span>
          </div>
        )}

      </div>
    </Dialog>

    <ConfirmDialog
      open={wideOpenConfirmOpen}
      onClose={() => setWideOpenConfirmOpen(false)}
      title="Save wide-open rule?"
      description="This rule has wildcard agent and no scope dimension. It will match every request of this action_type."
      confirmLabel="Save rule"
      loadingLabel="Saving"
      confirmVariant="primary"
      loading={submitting}
      onConfirm={async () => {
        setWideOpenConfirmOpen(false);
        await performSave();
      }}
    >
      <p className="text-sm text-[var(--muted-fg)]">
        Consider narrowing scope to a page, module type, or specific agent before saving.
      </p>
    </ConfirmDialog>

    <ConfirmDialog
      open={wildcardConfirmOpen}
      onClose={() => setWildcardConfirmOpen(false)}
      title="Apply to any agent?"
      description="This rule will apply to every registered agent, including ones you add later."
      confirmLabel="Use any agent"
      confirmVariant="primary"
      onConfirm={() => {
        setConfirmingWildcardAgent(true);
        patch({ agent_id: "*" });
        setWildcardConfirmOpen(false);
      }}
    />
    </>
  );
}
