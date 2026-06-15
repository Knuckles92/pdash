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
  "h-9 rounded-md border border-[var(--border)] bg-[var(--bg)] px-2 text-sm";

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

  return (
    <>
    <Dialog
      open={open}
      onClose={onClose}
      title={mode.kind === "create" ? "New approval rule" : "Edit approval rule"}
      description={
        isBuiltin
          ? "Built-in rule: scope and outcome are locked; only enable/disable and priority can be edited."
          : "Pre-filled with the narrowest scope from this request. Widen if you want to cover more cases."
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
        {/* Agent */}
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
              Select an agent…
            </option>
            {agentOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {a.display_name}
              </option>
            ))}
            <option value="*">* (any agent)</option>
          </select>
        </div>

        {/* Action type */}
        <div className="flex flex-col gap-1">
          <Label>Action type</Label>
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
                {at}
              </option>
            ))}
          </select>
        </div>

        {/* Scope */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div className="flex flex-col gap-1">
            <Label>Module ID</Label>
            <Input
              placeholder="mod_… (optional)"
              value={draft.module_id ?? ""}
              disabled={isBuiltin}
              onChange={(e) => patch({ module_id: e.target.value || null })}
            />
          </div>
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
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div className="flex flex-col gap-1">
            <Label>Owner scope</Label>
            <select
              className={SELECT_CLASS}
              value={draft.owner_scope ?? "any"}
              disabled={isBuiltin}
              onChange={(e) =>
                patch({ owner_scope: e.target.value as "any" | "self" | "other" })
              }
            >
              <option value="any">any</option>
              <option value="self">self (agent owns target)</option>
              <option value="other">other</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <Label>Outcome</Label>
            <select
              className={SELECT_CLASS}
              value={draft.outcome}
              disabled={isBuiltin}
              onChange={(e) =>
                patch({ outcome: e.target.value as "auto_approve" | "deny" | "prompt" })
              }
            >
              <option value="auto_approve">auto_approve</option>
              <option value="deny">deny</option>
              <option value="prompt">prompt</option>
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

        <div className="flex items-center gap-2">
          <input
            id="rule-enabled"
            type="checkbox"
            checked={draft.enabled ?? true}
            onChange={(e) => patch({ enabled: e.target.checked })}
          />
          <Label htmlFor="rule-enabled">Enabled</Label>
        </div>

        <div className="flex flex-col gap-1">
          <Label>Notes</Label>
          <Textarea
            rows={2}
            value={draft.notes ?? ""}
            onChange={(e) => patch({ notes: e.target.value || null })}
            placeholder="Optional rationale shown next to the rule"
          />
        </div>

        {isWideOpen && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="size-4 shrink-0 mt-0.5" />
            <span>
              Wildcard agent and no scope dimension means this rule fires for{" "}
              <em>every</em> request of action_type{" "}
              <code className="font-mono">{draft.action_type}</code>. You will be
              asked to confirm on save.
            </span>
          </div>
        )}

        {mode.kind === "create" && pendingMatchCount !== undefined && (
          <div className="flex items-center gap-2 rounded-md border border-[var(--border)] p-2">
            <input
              id="apply-pending"
              type="checkbox"
              checked={applyToPending}
              onChange={(e) => setApplyToPending(e.target.checked)}
            />
            <Label htmlFor="apply-pending" className="text-xs">
              Apply this rule to current matching pending requests ({pendingMatchCount} match)
            </Label>
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
      description="Selecting '* (any agent)' makes this rule apply to every registered agent — including ones you add later."
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
