/**
 * Typed fetch wrapper for the pdash backend.
 *
 * On the client: same-origin (Next.js rewrites /api/* → backend). Cookies
 * (session + csrf_token) ride along automatically. State-changing requests
 * auto-attach the X-CSRF-Token header from the csrf_token cookie.
 *
 * On the server (RSC / Route Handlers): pass `cookieHeader` to forward the
 * caller's cookies upstream — see `lib/session.ts`.
 */
import { CSRF_COOKIE, readCookie } from "./cookies";

export type About = {
  version: string;
};

export type McpTool = {
  name: string;
  description: string;
  category: "read" | "write" | "bootstrap";
};

export type McpStatus = {
  reachable: boolean;
  error: string | null;
  mcp_url: string;
  mcp_version: string | null;
  sse_connected: boolean | null;
  auth_cache_ttl_s: number | null;
  idem_dedupe_ttl_s: number | null;
  tools: McpTool[];
  backend_version: string;
  service_secret_configured: boolean;
  screenshot_sidecar: {
    configured: boolean;
    reachable: boolean | null;
  };
};

export type ProblemDetail = {
  type?: string;
  title: string;
  status: number;
  code: string;
  detail?: string;
  instance?: string;
  [key: string]: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: ProblemDetail | null;

  constructor(message: string, status: number, code: string, problem: ProblemDetail | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.problem = problem;
  }
}

/**
 * Extract a user-facing message from a thrown value, falling back to `fallback`.
 * `ApiError` extends `Error`, so this covers API and generic errors alike.
 */
export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

const MUTATING = new Set(["POST", "PATCH", "PUT", "DELETE"]);

export type ApiRequestInit = Omit<RequestInit, "body"> & {
  json?: unknown;
  /** Forward this Cookie header on the server. Ignored on the client. */
  cookieHeader?: string;
};

function apiBase(): string {
  // On the server (RSC / route handlers): need an absolute URL because Node's
  // fetch can't resolve relative paths. Default to the local backend; override
  // with PDASH_BACKEND_URL in Docker / different host.
  if (typeof window === "undefined") {
    return process.env.PDASH_BACKEND_URL ?? "http://localhost:8080";
  }
  // In the browser: same origin (proxied by next.config rewrites). Allow
  // opt-out for cross-origin dev.
  return process.env.NEXT_PUBLIC_API_URL ?? "";
}

export async function apiFetch<T = unknown>(
  path: string,
  init: ApiRequestInit = {},
): Promise<T> {
  const { json, cookieHeader, headers: hdrs, ...rest } = init;
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(hdrs);

  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (MUTATING.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  if (cookieHeader) {
    headers.set("Cookie", cookieHeader);
  }

  const url = path.startsWith("http") ? path : `${apiBase()}${path}`;
  const res = await fetch(url, {
    ...rest,
    method,
    headers,
    body: json !== undefined ? JSON.stringify(json) : (init as RequestInit).body,
    credentials: "include",
    cache: "no-store",
  });

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get("content-type") ?? "";
  const isJson = contentType.includes("json");

  if (!res.ok) {
    let problem: ProblemDetail | null = null;
    if (isJson) {
      try {
        problem = (await res.json()) as ProblemDetail;
      } catch {
        problem = null;
      }
    }
    const code = problem?.code ?? `http.${res.status}`;
    const message = problem?.detail ?? problem?.title ?? `HTTP ${res.status}`;
    throw new ApiError(message, res.status, code, problem);
  }

  if (!isJson) {
    return (await res.text()) as T;
  }
  return (await res.json()) as T;
}

// ---- Concrete endpoint helpers ----------------------------------------------

export type User = { user_id: string; kind: string; name: string };

export type CursorPage<T> = { items: T[]; next_cursor: string | null };

export type Page = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  type: string;
  owner_kind: string | null;
  owner_id: string | null;
  created_at: string;
  deleted_at: string | null;
};

export type Module = {
  id: string;
  type: string;
  title: string | null;
  owner_kind: string;
  owner_id: string;
  page_id: string;
  position: number;
  grid: Record<string, unknown> | null;
  permissions: Record<string, unknown>;
  data: Record<string, unknown>;
  config: Record<string, unknown>;
  schema_version: number;
  version: number;
  created_at: string;
  updated_at: string;
  last_updated_by: string;
  deleted_at: string | null;
};

export type PageAgentAccessLevel = "default" | "free" | "blocked" | "custom";

export type PageAgentAccessItem = {
  agent_id: string;
  display_name: string;
  status: "active" | "disabled" | "revoked";
  module_count: number;
  access: PageAgentAccessLevel;
  custom_rule_count: number;
};

export type Agent = {
  id: string;
  display_name: string;
  description: string | null;
  permissions: Record<string, unknown>;
  status: "active" | "disabled" | "revoked";
  created_at: string;
  last_active_at: string | null;
  last_key_rotated_at: string | null;
};

export type AgentKeyOut = { agent: Agent; api_key: string };

export type AgentRegistrationStatus =
  | "pending"
  | "approved"
  | "denied"
  | "claimed"
  | "expired";

export type AgentRegistration = {
  id: string;
  requested_name: string;
  description: string | null;
  rationale: string | null;
  client_hint: string | null;
  status: AgentRegistrationStatus;
  agent_id: string | null;
  permissions: Record<string, unknown> | null;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  decision_reason: string | null;
  claimed_at: string | null;
  expires_at: string | null;
};

export type ModuleSchemaEntry = {
  type: string;
  data?: Record<string, unknown>;
  config?: Record<string, unknown>;
  data_schema: Record<string, unknown>;
  config_schema: Record<string, unknown>;
};

// ---- Iframe allowlist ------------------------------------------------------

export type IframeAllowlistEntry = {
  id: number;
  host_pattern: string;
  path_prefix: string | null;
  description: string | null;
  added_at: string;
};

export type IframeAllowlistDraft = {
  host_pattern: string;
  path_prefix?: string | null;
  description?: string | null;
};

// ---- Action targets --------------------------------------------------------

export type ActionTargetKind = "webhook" | "local_script" | "mcp_tool" | "agent_message";
export type ActionTargetMode = "sync" | "async";

export type ActionTarget = {
  id: string;
  name: string;
  kind: ActionTargetKind;
  config: Record<string, unknown>;
  mode: ActionTargetMode;
  enabled: boolean;
  created_at: string;
  deleted_at: string | null;
};

export type ActionTargetDraft = {
  name: string;
  kind: ActionTargetKind;
  config: Record<string, unknown>;
  mode?: ActionTargetMode;
  enabled?: boolean;
};

export type ActionTargetUpdate = {
  name?: string;
  config?: Record<string, unknown>;
  mode?: ActionTargetMode;
  enabled?: boolean;
};

export type ActionTargetTestResult = {
  ok: boolean;
  message: string;
  details?: Record<string, unknown> | null;
};

export type FireActionButtonResult = {
  ok: boolean;
  result: Record<string, unknown>;
  module_version: number;
};

// ---- Approvals --------------------------------------------------------------

export type ApprovalActionType =
  | "create_module"
  | "update_module_data"
  | "update_module_config"
  | "update_module_meta"
  | "delete_module"
  | "create_page"
  | "delete_page"
  | "fire_action_button"
  | "register_agent";

export const APPROVAL_ACTION_TYPES: readonly ApprovalActionType[] = [
  "create_module",
  "update_module_data",
  "update_module_config",
  "update_module_meta",
  "delete_module",
  "create_page",
  "delete_page",
  "fire_action_button",
  "register_agent",
] as const;

export type ApprovalRequestStatus =
  | "pending"
  | "approved"
  | "denied"
  | "applied"
  | "application_failed"
  | "superseded"
  | "expired";

export type ApprovalRequest = {
  id: string;
  agent_id: string | null;
  action_type: string;
  target_kind: string | null;
  target_id: string | null;
  proposed_payload: Record<string, unknown>;
  idempotency_key: string | null;
  status: ApprovalRequestStatus;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  decision_reason: string | null;
  applied_at: string | null;
  executed_at: string | null;
  execution_result: Record<string, unknown> | null;
  expires_at: string | null;
};

export type ApprovalRequestDetail = ApprovalRequest & {
  diff_preview: Record<string, unknown> | null;
  dashboard_preview: DashboardPreview | null;
  action_preview: ActionPreview | null;
  file_preview: FilePreview | null;
  registration_preview: RegistrationPreview | null;
};

export type ActionPreview = {
  target: {
    id: string;
    name: string;
    kind: ActionTargetKind;
    mode: ActionTargetMode;
    enabled: boolean;
  };
  destination: string | null;
  payload: Record<string, unknown>;
  uses_target_default: boolean;
};

export type FilePreview = {
  display_name: string | null;
  inbox_name: string | null;
  kind: FileKind | null;
  mime: string | null;
  size_bytes: number | null;
  purpose: string | null;
  sha256: string | null;
  page: { id: string; name: string; slug: string } | null;
};

export type RegistrationPreview = {
  registration_id: string | null;
  requested_name: string | null;
  description: string | null;
  rationale: string | null;
  client_hint: string | null;
  status: string | null;
  expires_at: string | null;
};

export type DashboardPreviewHighlight = {
  module_ids: string[];
  removed_module_ids: string[];
  removed_modules?: Module[];
  change: "create" | "update" | "delete" | "create_page";
};

export type DashboardPreview = {
  page: { id: string; name: string; slug: string; description?: string | null; type?: string };
  modules: Module[];
  highlight: DashboardPreviewHighlight;
};

export type ApprovalRequestList = {
  items: ApprovalRequest[];
  next_cursor: string | null;
  total_pending: number | null;
};

export type ApprovalRuleDraft = {
  agent_id: string;
  action_type: string;
  module_type?: string | null;
  module_id?: string | null;
  page_id?: string | null;
  owner_scope?: "any" | "self" | "other";
  outcome: "auto_approve" | "deny" | "prompt";
  priority?: number;
  notes?: string | null;
  enabled?: boolean;
  apply_to_pending?: boolean;
};

export type ApprovalRule = {
  id: string;
  agent_id: string;
  action_type: string;
  module_type: string | null;
  module_id: string | null;
  page_id: string | null;
  owner_scope: string;
  outcome: "auto_approve" | "deny" | "prompt";
  priority: number;
  is_builtin: boolean;
  enabled: boolean;
  notes: string | null;
  created_at: string;
  created_by: string;
  last_applied_at: string | null;
  application_count: number;
};

export type ApprovalRulePreview = {
  rule_id: string;
  scanned: number;
  matched: number;
  items: Array<{
    request_id: string;
    agent_id: string;
    status: string;
    would_have_outcome: string;
    created_at: string;
  }>;
};

export type ActivityLogRow = {
  id: number;
  timestamp: string;
  actor_kind: string;
  actor_id: string | null;
  action_type: string;
  target_kind: string | null;
  target_id: string | null;
  payload_summary: Record<string, unknown> | null;
  outcome: string;
  request_id: string | null;
  rule_id: string | null;
  error_detail: string | null;
};

export type ActivityLogPage = {
  items: ActivityLogRow[];
  next_cursor: string | null;
};

export type ActivityLogDetail = ActivityLogRow & {
  audit_blob?: Record<string, unknown> | { _raw: string };
};

/**
 * Build a `?a=b&c=d` query string from a params object, skipping values that are
 * `undefined`, `null`, or `""`. Booleans and numbers (including `false`/`0`) are
 * kept. Returns `""` when no params survive.
 */
// ---- files (agent file-drop) -----------------------------------------------
export type FileKind = "image" | "document";

export type RegisteredFile = {
  id: string;
  agent_id: string | null;
  inbox_name: string;
  display_name: string;
  sha256: string;
  size_bytes: number;
  mime: string;
  kind: FileKind;
  status: string;
  page_id: string | null;
  purpose: string | null;
  created_at: string;
  updated_at: string;
  url: string;
  present_on_disk?: boolean;
};

export type InboxFile = {
  name: string;
  page_id: string | null;
  size_bytes: number;
  modified_at: string;
  mime: string;
  kind: FileKind;
  status: "unclaimed" | "pending_registration";
  request_id: string | null;
};

export type StoreOrphan = { file_id: string; size_bytes: number };

export type FilesOverview = {
  files: RegisteredFile[];
  inbox: InboxFile[];
  store_orphans: StoreOrphan[];
  counts: Record<string, number>;
  scan_truncated: boolean;
  total_unclaimed: number;
};

export type OrphanCount = {
  unclaimed: number;
  pending: number;
  missing: number;
  total: number;
};

function buildQuery(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    usp.set(key, String(value));
  }
  const query = usp.toString();
  return query ? `?${query}` : "";
}

export const api = {
  // auth
  login: (password: string) =>
    apiFetch<{ user: User }>("/api/v1/auth/login", {
      method: "POST",
      json: { password },
    }),
  logout: () => apiFetch<void>("/api/v1/auth/logout", { method: "POST" }),
  me: (opts: ApiRequestInit = {}) => apiFetch<User>("/api/v1/auth/me", opts),

  // pages
  listPages: (opts: ApiRequestInit = {}) =>
    apiFetch<CursorPage<Page>>("/api/v1/pages?limit=200", opts),
  getPageBySlug: (slug: string, opts: ApiRequestInit = {}) =>
    apiFetch<Page>(`/api/v1/pages/by-slug/${encodeURIComponent(slug)}`, opts),
  createPage: (body: {
    slug: string;
    name: string;
    description?: string;
    type?: string;
  }) => apiFetch<Page>("/api/v1/pages", { method: "POST", json: body }),
  updatePage: (id: string, body: Partial<{ slug: string; name: string; description: string }>) =>
    apiFetch<Page>(`/api/v1/pages/${id}`, { method: "PATCH", json: body }),
  deletePage: (id: string) =>
    apiFetch<void>(`/api/v1/pages/${id}`, { method: "DELETE" }),
  clearHomeExamples: (pageId: string) =>
    apiFetch<{ cleared: number }>(`/api/v1/pages/${pageId}/default-examples`, {
      method: "DELETE",
    }),
  deployHomeExamples: (pageId: string) =>
    apiFetch<{ deployed: number }>(`/api/v1/pages/${pageId}/default-examples`, {
      method: "POST",
    }),
  getPageAgentAccess: (pageId: string, opts: ApiRequestInit = {}) =>
    apiFetch<{ page_id: string; items: PageAgentAccessItem[] }>(
      `/api/v1/pages/${pageId}/agent-access`,
      opts,
    ),
  setPageAgentAccess: (
    pageId: string,
    agentId: string,
    access: "default" | "free" | "blocked",
  ) =>
    apiFetch<PageAgentAccessItem>(`/api/v1/pages/${pageId}/agent-access/${agentId}`, {
      method: "PUT",
      json: { access },
    }),

  // modules
  listModules: (params: { page_id?: string; type?: string } = {}, opts: ApiRequestInit = {}) => {
    return apiFetch<CursorPage<Module>>(
      `/api/v1/modules${buildQuery({ page_id: params.page_id, type: params.type, limit: 200 })}`,
      opts,
    );
  },
  createModule: (body: {
    type: string;
    page_id: string;
    title?: string;
    data: Record<string, unknown>;
    config: Record<string, unknown>;
    position?: number;
    grid?: Record<string, unknown>;
  }) => apiFetch<Module>("/api/v1/modules", { method: "POST", json: body }),
  patchModule: (
    id: string,
    body: Partial<{
      title: string;
      data: unknown;
      config: unknown;
      position: number;
      grid: Record<string, unknown>;
    }>,
  ) => apiFetch<Module>(`/api/v1/modules/${id}`, { method: "PATCH", json: body }),
  deleteModule: (id: string) =>
    apiFetch<void>(`/api/v1/modules/${id}`, { method: "DELETE" }),
  reorderModules: (page_id: string, ids: string[]) =>
    apiFetch<{ reordered: number }>("/api/v1/modules/reorder", {
      method: "POST",
      json: { page_id, ids },
    }),

  // agents
  listAgents: (opts: ApiRequestInit = {}) =>
    apiFetch<CursorPage<Agent>>("/api/v1/agents?limit=200", opts),
  createAgent: (body: { display_name: string; description?: string }) =>
    apiFetch<AgentKeyOut>("/api/v1/agents", { method: "POST", json: body }),
  rotateAgentKey: (id: string) =>
    apiFetch<AgentKeyOut>(`/api/v1/agents/${id}/rotate-key`, { method: "POST" }),
  enableAgent: (id: string) =>
    apiFetch<Agent>(`/api/v1/agents/${id}/enable`, { method: "POST" }),
  disableAgent: (id: string) =>
    apiFetch<Agent>(`/api/v1/agents/${id}/disable`, { method: "POST" }),
  revokeAgent: (id: string) =>
    apiFetch<void>(`/api/v1/agents/${id}`, { method: "DELETE" }),

  // agent self-registration (list/history; decisions go through Approvals inbox)
  listAgentRegistrations: (params: { status?: string } = {}, opts: ApiRequestInit = {}) =>
    apiFetch<{ items: AgentRegistration[] }>(
      `/api/v1/agent-registrations${buildQuery({ status: params.status })}`,
      opts,
    ),

  // module schemas
  getModuleSchema: (type: string, opts: ApiRequestInit = {}) =>
    apiFetch<ModuleSchemaEntry>(`/api/v1/module-schemas/${type}`, opts),

  // iframe allowlist
  listIframeAllowlist: (opts: ApiRequestInit = {}) =>
    apiFetch<IframeAllowlistEntry[]>("/api/v1/iframe-allowlist", opts),
  addIframeAllowlist: (body: IframeAllowlistDraft) =>
    apiFetch<IframeAllowlistEntry>("/api/v1/iframe-allowlist", {
      method: "POST",
      json: body,
    }),
  removeIframeAllowlist: (id: number) =>
    apiFetch<void>(`/api/v1/iframe-allowlist/${id}`, { method: "DELETE" }),

  // files (agent file-drop): registered files + inbox orphan reconciliation
  listFiles: (opts: ApiRequestInit = {}) =>
    apiFetch<FilesOverview>("/api/v1/files", opts),
  orphanCount: (opts: ApiRequestInit = {}) =>
    apiFetch<OrphanCount>("/api/v1/files/orphan-count", opts),
  registerInboxFile: (body: {
    name: string;
    display_name: string;
    page_id?: string;
    purpose?: string;
  }) => apiFetch<RegisteredFile>("/api/v1/files/inbox/register", { method: "POST", json: body }),
  deleteInboxFile: (body: { name: string; page_id?: string }) =>
    apiFetch<void>("/api/v1/files/inbox/delete", { method: "POST", json: body }),
  deleteFile: (id: string) =>
    apiFetch<void>(`/api/v1/files/${id}`, { method: "DELETE" }),

  // action targets
  listActionTargets: (opts: ApiRequestInit = {}) =>
    apiFetch<CursorPage<ActionTarget>>("/api/v1/action-targets?limit=200", opts),
  getActionTarget: (id: string, opts: ApiRequestInit = {}) =>
    apiFetch<ActionTarget>(`/api/v1/action-targets/${id}`, opts),
  createActionTarget: (body: ActionTargetDraft) =>
    apiFetch<ActionTarget>("/api/v1/action-targets", { method: "POST", json: body }),
  patchActionTarget: (id: string, body: ActionTargetUpdate) =>
    apiFetch<ActionTarget>(`/api/v1/action-targets/${id}`, {
      method: "PATCH",
      json: body,
    }),
  deleteActionTarget: (id: string) =>
    apiFetch<void>(`/api/v1/action-targets/${id}`, { method: "DELETE" }),
  testActionTarget: (id: string) =>
    apiFetch<ActionTargetTestResult>(`/api/v1/action-targets/${id}/test`, {
      method: "POST",
    }),

  // admin firing of an action_button module
  fireActionButtonModule: (id: string, payload?: Record<string, unknown>) =>
    apiFetch<FireActionButtonResult>(`/api/v1/modules/${id}/fire`, {
      method: "POST",
      json: { payload: payload ?? {} },
    }),

  // approval requests
  listApprovalRequests: (
    params: {
      status?: string;
      agent_id?: string;
      action_type?: string;
      page_id?: string;
      created_after?: string;
      created_before?: string;
      cursor?: string;
      limit?: number;
    } = {},
    opts: ApiRequestInit = {},
  ) => {
    return apiFetch<ApprovalRequestList>(
      `/api/v1/approval-requests${buildQuery({
        status: params.status,
        agent_id: params.agent_id,
        action_type: params.action_type,
        page_id: params.page_id,
        created_after: params.created_after,
        created_before: params.created_before,
        cursor: params.cursor,
        limit: params.limit ?? 50,
      })}`,
      opts,
    );
  },
  getApprovalRequest: (id: string, opts: ApiRequestInit = {}) =>
    apiFetch<ApprovalRequestDetail>(`/api/v1/approval-requests/${id}`, opts),
  approveRequest: (
    id: string,
    body: {
      reason?: string;
      create_rule?: ApprovalRuleDraft;
      registration?: {
        display_name?: string;
        description?: string;
        permissions?: Record<string, unknown>;
      };
    } = {},
  ) =>
    apiFetch<{
      request: ApprovalRequest;
      applied: boolean;
      audit_id: number;
      rule?: { id: string; agent_id: string; action_type: string; outcome: string };
      apply_result?: Record<string, unknown>;
      error?: string;
    }>(`/api/v1/approval-requests/${id}/approve`, { method: "POST", json: body }),
  denyRequest: (
    id: string,
    body: { reason?: string; create_rule?: ApprovalRuleDraft } = {},
  ) =>
    apiFetch<{
      request: ApprovalRequest;
      audit_id: number;
      rule?: { id: string; agent_id: string; action_type: string; outcome: string };
    }>(`/api/v1/approval-requests/${id}/deny`, { method: "POST", json: body }),
  bulkDecideRequests: (
    decisions: Array<{ id: string; decision: "approve" | "deny"; reason?: string }>,
  ) =>
    apiFetch<{ results: Array<{ id: string; status: string; error: string | null }> }>(
      "/api/v1/approval-requests/bulk-decide",
      { method: "POST", json: { decisions } },
    ),

  // approval rules
  listApprovalRules: (
    params: {
      enabled?: boolean;
      agent_id?: string;
      action_type?: string;
      page_id?: string;
      cursor?: string;
      limit?: number;
    } = {},
    opts: ApiRequestInit = {},
  ) => {
    return apiFetch<CursorPage<ApprovalRule>>(
      `/api/v1/approval-rules${buildQuery({
        enabled: params.enabled,
        agent_id: params.agent_id,
        action_type: params.action_type,
        page_id: params.page_id,
        cursor: params.cursor,
        limit: params.limit ?? 200,
      })}`,
      opts,
    );
  },
  createApprovalRule: (body: ApprovalRuleDraft) =>
    apiFetch<{ rule: ApprovalRule; applied_to_pending: number }>(
      "/api/v1/approval-rules",
      { method: "POST", json: body },
    ),
  patchApprovalRule: (
    id: string,
    body: Partial<{
      agent_id: string;
      module_type: string | null;
      module_id: string | null;
      page_id: string | null;
      owner_scope: "any" | "self" | "other";
      outcome: "auto_approve" | "deny" | "prompt";
      priority: number;
      notes: string | null;
      enabled: boolean;
    }>,
  ) =>
    apiFetch<ApprovalRule>(`/api/v1/approval-rules/${id}`, {
      method: "PATCH",
      json: body,
    }),
  deleteApprovalRule: (id: string) =>
    apiFetch<void>(`/api/v1/approval-rules/${id}`, { method: "DELETE" }),
  previewApprovalRule: (id: string, limit = 100) =>
    apiFetch<ApprovalRulePreview>(
      `/api/v1/approval-rules/${id}/preview?limit=${limit}`,
      { method: "POST" },
    ),
  revokeApprovalRule: (id: string, reverse_decisions = false) =>
    apiFetch<{ rule: ApprovalRule; reversed: number }>(
      `/api/v1/approval-rules/${id}/revoke?reverse_decisions=${reverse_decisions}`,
      { method: "POST" },
    ),

  // activity log
  listActivity: (
    params: {
      kind?: string;
      outcome?: string;
      actor?: string;
      target_kind?: string;
      target_id?: string;
      q?: string;
      after?: string;
      before?: string;
      cursor?: string;
      limit?: number;
    } = {},
    opts: ApiRequestInit = {},
  ) => {
    return apiFetch<ActivityLogPage>(
      `/api/v1/activity-log${buildQuery({
        kind: params.kind,
        outcome: params.outcome,
        actor: params.actor,
        target_kind: params.target_kind,
        target_id: params.target_id,
        q: params.q,
        after: params.after,
        before: params.before,
        cursor: params.cursor,
        limit: params.limit ?? 50,
      })}`,
      opts,
    );
  },
  getActivity: (id: number, opts: ApiRequestInit = {}) =>
    apiFetch<ActivityLogDetail>(`/api/v1/activity-log/${id}`, opts),

  getAbout: (opts: ApiRequestInit = {}) => apiFetch<About>("/api/v1/about", opts),

  // mcp control center
  getMcpStatus: (opts: ApiRequestInit = {}) =>
    apiFetch<McpStatus>("/api/v1/mcp/status", opts),
};
