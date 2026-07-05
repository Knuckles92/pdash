/**
 * Shared vocabulary for the activity feed: action-type groups for filtering,
 * plain-language verbs for rows, and outcome presentation (label + dot tone).
 * The raw `action_type` / `outcome` strings stay visible in the UI's mono
 * voice; these maps only add the readable layer on top.
 */

export type ActionGroup = {
  key: string;
  label: string;
  kinds: string[];
};

export const ACTION_GROUPS: ActionGroup[] = [
  {
    key: "modules",
    label: "Modules",
    kinds: [
      "create_module",
      "update_module_data",
      "update_module_config",
      "update_module_meta",
      "delete_module",
    ],
  },
  {
    key: "pages",
    label: "Pages",
    kinds: ["create_page", "delete_page"],
  },
  {
    key: "actions",
    label: "Action buttons",
    kinds: ["fire_action_button"],
  },
  {
    key: "rules",
    label: "Approval rules",
    kinds: [
      "create_approval_rule",
      "update_approval_rule",
      "delete_approval_rule",
      "revoke_approval_rule",
    ],
  },
];

export const ALL_KINDS: string[] = ACTION_GROUPS.flatMap((g) => g.kinds);

/** Row sentence: `{actor} {verb} {target}` — verbs read without a preposition. */
export const ACTION_VERBS: Record<string, string> = {
  create_module: "created module",
  update_module_data: "updated data",
  update_module_config: "updated config",
  update_module_meta: "updated details",
  delete_module: "deleted module",
  create_page: "created page",
  delete_page: "deleted page",
  fire_action_button: "fired action",
  create_approval_rule: "created rule",
  update_approval_rule: "updated rule",
  delete_approval_rule: "deleted rule",
  revoke_approval_rule: "revoked rule",
};

export function actionVerb(actionType: string): string {
  return ACTION_VERBS[actionType] ?? actionType.replaceAll("_", " ");
}

export type OutcomeMeta = {
  value: string;
  label: string;
  /** Solid dot color for timeline + rail toggles. */
  dotClass: string;
  /** Text color for the inline outcome word on non-applied rows. */
  textClass: string;
};

export const OUTCOMES: OutcomeMeta[] = [
  {
    value: "applied",
    label: "Applied",
    dotClass: "bg-[var(--success)]",
    textClass: "text-[var(--success)]",
  },
  {
    value: "auto_approved",
    label: "Auto-approved",
    dotClass: "bg-[var(--success)]",
    textClass: "text-[var(--success)]",
  },
  {
    value: "queued",
    label: "Queued",
    dotClass: "bg-[var(--warning)]",
    textClass: "text-[var(--warning)]",
  },
  {
    value: "denied",
    label: "Denied",
    dotClass: "bg-[var(--danger)]",
    textClass: "text-[var(--danger)]",
  },
  {
    value: "error",
    label: "Error",
    dotClass: "bg-[var(--danger)]",
    textClass: "text-[var(--danger)]",
  },
];

export function outcomeMeta(outcome: string): OutcomeMeta {
  return (
    OUTCOMES.find((o) => o.value === outcome) ?? {
      value: outcome,
      label: outcome.replaceAll("_", " "),
      dotClass: "bg-[var(--muted-fg)]",
      textClass: "text-[var(--muted-fg)]",
    }
  );
}
