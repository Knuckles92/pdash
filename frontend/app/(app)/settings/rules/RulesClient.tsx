"use client";

import { Eye, Pencil, Plus, Shield, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { RuleEditor } from "@/components/approvals/RuleEditor";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Sheet } from "@/components/ui/Sheet";
import {
  api,
  errorMessage,
  type Agent,
  type ApprovalRuleDraft,
  type ApprovalRule,
  type ApprovalRulePreview,
  type Page,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { upsertById } from "@/lib/collections";
import { relativeTime } from "@/lib/time";

type RulesClientProps = {
  initialRules: ApprovalRule[];
  agents: Agent[];
  pages: Page[];
  pageId?: string | null;
};

function scopeSummary(rule: ApprovalRule, pagesById: Map<string, Page>): string {
  const parts: string[] = [];
  if (rule.module_id) parts.push(`module:${rule.module_id.slice(-6)}`);
  if (rule.page_id) {
    parts.push(`page:${pagesById.get(rule.page_id)?.name ?? rule.page_id.slice(-6)}`);
  }
  if (rule.module_type) parts.push(`type:${rule.module_type}`);
  if (rule.owner_scope && rule.owner_scope !== "any") parts.push(`owner:${rule.owner_scope}`);
  if (parts.length === 0) return "*";
  return parts.join(" ");
}

function outcomeTone(outcome: string): "success" | "danger" | "warning" | "neutral" {
  switch (outcome) {
    case "auto_approve":
      return "success";
    case "deny":
      return "danger";
    case "prompt":
      return "warning";
    default:
      return "neutral";
  }
}

/**
 * Compute which rules are shadowed by a strictly more-specific rule (same
 * action_type, scope is a superset, equal or higher priority). Best-effort
 * client-side detection.
 */
function computeShadows(rules: ApprovalRule[]): Map<string, string> {
  const shadows = new Map<string, string>();
  const enabled = rules.filter((rule) => rule.enabled);
  for (const candidate of enabled) {
    for (const other of enabled) {
      if (other.id === candidate.id) continue;
      if (other.action_type !== candidate.action_type) continue;
      // `other` is more specific if every set scope dimension of candidate is
      // either the same as other's, or other narrows it further.
      const moreSpecific =
        scopeSpecificity(other) > scopeSpecificity(candidate) &&
        scopeSubsumes(candidate, other) &&
        other.priority <= candidate.priority;
      if (moreSpecific) {
        shadows.set(candidate.id, other.id);
        break;
      }
    }
  }
  return shadows;
}

function scopeSpecificity(rule: ApprovalRule): number {
  return (
    (rule.module_id ? 16 : 0) +
    (rule.page_id ? 8 : 0) +
    (rule.module_type ? 4 : 0) +
    (rule.agent_id !== "*" ? 2 : 0) +
    (rule.owner_scope && rule.owner_scope !== "any" ? 1 : 0)
  );
}

function scopeSubsumes(broader: ApprovalRule, narrower: ApprovalRule): boolean {
  // narrower must satisfy every set dimension of broader.
  if (broader.agent_id !== "*" && broader.agent_id !== narrower.agent_id) return false;
  if (broader.module_id && broader.module_id !== narrower.module_id) return false;
  if (broader.page_id && broader.page_id !== narrower.page_id) return false;
  if (broader.module_type && broader.module_type !== narrower.module_type)
    return false;
  if (
    broader.owner_scope &&
    broader.owner_scope !== "any" &&
    broader.owner_scope !== narrower.owner_scope
  ) {
    return false;
  }
  return true;
}

export function RulesClient({ initialRules, agents, pages, pageId = null }: RulesClientProps) {
  const [rules, setRules] = useState<ApprovalRule[]>(initialRules);
  const [editorMode, setEditorMode] = useState<
    | null
    | { kind: "create"; draft?: Partial<ApprovalRuleDraft> }
    | { kind: "edit"; rule: ApprovalRule }
  >(null);
  const [preview, setPreview] = useState<ApprovalRulePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [ruleToDelete, setRuleToDelete] = useState<ApprovalRule | null>(null);
  const [deleting, setDeleting] = useState(false);

  const agentsById = useMemo(() => {
    const m = new Map<string, Agent>();
    for (const a of agents) m.set(a.id, a);
    return m;
  }, [agents]);
  const pagesById = useMemo(() => {
    const m = new Map<string, Page>();
    for (const p of pages) m.set(p.id, p);
    return m;
  }, [pages]);
  const selectedPage = pageId ? pagesById.get(pageId) : undefined;
  const selectedPageLabel = selectedPage?.name ?? (pageId ? `page ${pageId.slice(-6)}` : "");
  const shadows = useMemo(() => computeShadows(rules), [rules]);
  const createDraft = pageId ? { page_id: pageId } : undefined;

  useEffect(() => {
    setRules(initialRules);
  }, [initialRules]);

  // Allow deep-linking to a specific rule (?id=rule_xyz).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const id = params.get("id");
    if (id) {
      const r = rules.find((x) => x.id === id);
      if (r) setEditorMode({ kind: "edit", rule: r });
    }
  }, [rules]);

  function upsertLocal(rule: ApprovalRule): void {
    setRules((prev) => upsertById(prev, rule).sort((a, b) => a.priority - b.priority));
  }

  function handleSaved(rule: ApprovalRule): void {
    if (pageId && rule.page_id !== pageId) {
      setRules((prev) => prev.filter((r) => r.id !== rule.id));
      return;
    }
    upsertLocal(rule);
  }

  async function toggleRule(rule: ApprovalRule, enabled: boolean): Promise<void> {
    try {
      const next = await api.patchApprovalRule(rule.id, { enabled });
      upsertLocal(next);
      toast.success(enabled ? "Rule enabled" : "Rule disabled");
    } catch (err) {
      toast.error(errorMessage(err, "Failed"));
    }
  }

  async function confirmDeleteRule() {
    if (!ruleToDelete || ruleToDelete.is_builtin) return;
    setDeleting(true);
    try {
      await api.deleteApprovalRule(ruleToDelete.id);
      setRules((prev) => prev.filter((x) => x.id !== ruleToDelete.id));
      toast.success("Rule deleted");
      setRuleToDelete(null);
    } catch (err) {
      toast.error(errorMessage(err, "Delete failed"));
    } finally {
      setDeleting(false);
    }
  }

  async function previewRule(rule: ApprovalRule): Promise<void> {
    setPreviewLoading(true);
    setPreview(null);
    try {
      const res = await api.previewApprovalRule(rule.id);
      setPreview(res);
    } catch (err) {
      toast.error(errorMessage(err, "Preview failed"));
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            {pageId
              ? `Approval rules for ${selectedPageLabel}`
              : "Approval rules (sorted by priority asc)"}
          </h2>
          {pageId && (
            <p className="text-xs text-[var(--muted-fg)]">
              Sorted by priority asc
            </p>
          )}
        </div>
        <Button size="sm" onClick={() => setEditorMode({ kind: "create", draft: createDraft })}>
          <Plus className="size-4" /> New rule
        </Button>
      </div>

      {rules.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck className="size-12" />}
          title={pageId ? "No rules for this page" : "No rules configured"}
          hint={
            pageId
              ? "Create a rule to scope approval behavior to this page."
              : "Rules let agents auto-approve repeat actions. The built-in safety rules will run by default; add your own to bend the policy."
          }
          action={
            <Button onClick={() => setEditorMode({ kind: "create", draft: createDraft })}>
              <Plus className="size-4" /> New rule
            </Button>
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--border)] bg-[var(--muted)]/60 text-xs font-medium uppercase tracking-wide text-[var(--muted-fg)]">
                <tr>
                  <th className="text-left px-3 py-2">Pri</th>
                  <th className="text-left px-3 py-2">Agent</th>
                  <th className="text-left px-3 py-2">Action</th>
                  <th className="text-left px-3 py-2">Scope</th>
                  <th className="text-left px-3 py-2">Outcome</th>
                  <th className="text-left px-3 py-2 hidden lg:table-cell">Matched</th>
                  <th className="text-left px-3 py-2">Enabled</th>
                  <th className="text-right px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {rules.map((rule) => {
                  const agent =
                    rule.agent_id === "*"
                      ? "* (any)"
                      : agentsById.get(rule.agent_id)?.display_name ?? rule.agent_id;
                  const shadowedBy = shadows.get(rule.id);
                  return (
                    <tr
                      key={rule.id}
                      className={cn(
                        "transition-colors hover:bg-[var(--muted)]/60",
                        !rule.enabled && "opacity-60",
                      )}
                    >
                      <td className="px-3 py-2 font-mono text-xs">{rule.priority}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1">
                          <span className="truncate max-w-[10rem]">{agent}</span>
                          {rule.is_builtin && (
                            <Badge tone="info" className="text-[10px]">
                              built-in
                            </Badge>
                          )}
                          {shadowedBy && (
                            <Badge
                              tone="warning"
                              className="text-[10px]"
                              title={`Shadowed by ${shadowedBy}`}
                            >
                              shadowed
                            </Badge>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{rule.action_type}</td>
                      <td className="px-3 py-2 text-xs">{scopeSummary(rule, pagesById)}</td>
                      <td className="px-3 py-2">
                        <Badge tone={outcomeTone(rule.outcome)}>{rule.outcome}</Badge>
                      </td>
                      <td className="px-3 py-2 hidden lg:table-cell text-xs text-[var(--muted-fg)]">
                        {rule.application_count}× · {relativeTime(rule.last_applied_at)}
                      </td>
                      <td className="px-3 py-2">
                        <label className="inline-flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={rule.enabled}
                            onChange={(e) => void toggleRule(rule, e.target.checked)}
                          />
                        </label>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Preview"
                            onClick={() => void previewRule(rule)}
                            aria-label="Preview rule"
                          >
                            <Eye className="size-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Edit"
                            onClick={() => setEditorMode({ kind: "edit", rule })}
                            aria-label="Edit rule"
                          >
                            <Pencil className="size-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title={rule.is_builtin ? "Built-in rules cannot be deleted" : "Delete"}
                            disabled={rule.is_builtin}
                            onClick={() => setRuleToDelete(rule)}
                            aria-label="Delete rule"
                          >
                            <Trash2
                              className={cn(
                                "size-4",
                                !rule.is_builtin && "text-[var(--danger)]",
                              )}
                            />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <ConfirmDialog
        open={ruleToDelete !== null}
        onClose={() => setRuleToDelete(null)}
        title="Delete approval rule?"
        description={ruleToDelete ? `Delete rule ${ruleToDelete.id}?` : undefined}
        confirmLabel="Delete rule"
        loadingLabel="Deleting"
        icon={<Trash2 className="size-4" />}
        loading={deleting}
        onConfirm={confirmDeleteRule}
      />

      {editorMode && (
        <RuleEditor
          open={!!editorMode}
          onClose={() => setEditorMode(null)}
          mode={
            editorMode.kind === "create"
              ? { kind: "create", draft: editorMode.draft }
              : { kind: "edit", rule: editorMode.rule }
          }
          agents={agents}
          pages={pages}
          onSaved={handleSaved}
        />
      )}

      <Sheet
        open={previewLoading || !!preview}
        onClose={() => setPreview(null)}
        side="right"
        title={
          <span className="flex items-center gap-2">
            <Shield className="size-4" /> Rule preview
          </span>
        }
        description={
          preview
            ? `Scanned ${preview.scanned} historical requests · ${preview.matched} would have matched`
            : "Running…"
        }
      >
        {previewLoading ? (
          <p className="text-sm text-[var(--muted-fg)]">Loading preview…</p>
        ) : preview ? (
          <div className="flex flex-col gap-2">
            {preview.items.length === 0 ? (
              <p className="text-sm text-[var(--muted-fg)]">No historical matches.</p>
            ) : (
              <ul className="divide-y divide-[var(--border)]">
                {preview.items.map((m) => (
                  <li key={m.request_id} className="py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono">{m.request_id}</span>
                      <Badge tone={outcomeTone(m.would_have_outcome)}>
                        → {m.would_have_outcome}
                      </Badge>
                    </div>
                    <div className="mt-0.5 text-[var(--muted-fg)]">
                      {m.agent_id} · {m.status} · {relativeTime(m.created_at)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
