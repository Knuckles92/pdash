"use client";

import {
  Activity,
  Bot,
  Camera,
  Copy,
  Plug,
  RefreshCw,
  Server,
  Sparkles,
  Terminal,
  Wifi,
  WifiOff,
} from "lucide-react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { api, errorMessage, type Agent, type McpStatus, type McpTool } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/time";

const PUBLIC_MCP_URL_LS_KEY = "pdash.publicMcpUrl";

/** Append `/mcp` to a base URL (the FastMCP streamable-HTTP mount path). */
function withMcpPath(base: string | null | undefined): string {
  if (!base) return "";
  const trimmed = base.replace(/\/+$/, "");
  return trimmed.endsWith("/mcp") ? trimmed : `${trimmed}/mcp`;
}

function skillUrlFromMcpUrl(mcpUrl: string): string {
  const url = withMcpPath(mcpUrl);
  return url ? url.replace(/\/mcp$/, "/mcp-skill/SKILL.md") : "";
}

function buildOnboardingPrompt(mcpUrl: string, skillUrl: string): string {
  const url = mcpUrl || "<your pdash MCP URL>";
  const skill = skillUrl || "<your pdash skill file URL>";
  return `You are connecting to pdash, a self-hosted dashboard, over MCP.

First read and follow the hosted pdash skill file:
${skill}

If you cannot fetch that URL, use these fallback instructions.

Use MCP tools through your client's MCP integration — do NOT call the endpoint with
raw curl unless debugging.

1. Add the pdash MCP server to your client's MCP configuration first (streamable HTTP,
   no API key yet). Example:
   {
     "mcpServers": {
       "pdash": {
         "url": "${url}"
       }
     }
   }
   Reload or restart your MCP session so pdash tools appear. Gated tools will return
   auth_required until you finish step 6 — that is expected.

2. Call the \`onboarding\` tool to confirm connectivity and read the auth flow.

3. Call \`request_registration\` with a clear display name for yourself, e.g.
   request_registration(display_name="claude-code", description="what you are",
   rationale="why you need access"). This creates a PENDING request; it does NOT
   grant access yet. Save the returned claim_token.

4. Tell me you have requested access — I will approve it in pdash (Settings → Agents).
   Do NOT retry request_registration. Instead poll
   claim_registration(claim_token="<your token>") about every 10 seconds.

5. Once I approve, claim_registration returns your permanent API key (hb_agt_...).
   Update your MCP client config to add the key and reconnect, e.g.:
   {
     "mcpServers": {
       "pdash": {
         "url": "${url}",
         "headers": { "Authorization": "Bearer hb_agt_..." }
       }
     }
   }

6. The full tool set is now unlocked. Every write goes through my approval engine.`;
}

const REFRESH_MS = 5000;

type StatusTone = "success" | "warning" | "danger" | "neutral";

const TONE_SURFACE: Record<StatusTone, string> = {
  success: "border-[var(--success)]/25 bg-[var(--success-soft)] text-[var(--success)]",
  warning: "border-[var(--warning)]/25 bg-[var(--warning-soft)] text-[var(--warning)]",
  danger: "border-[var(--danger)]/25 bg-[var(--danger-soft)] text-[var(--danger)]",
  neutral: "border-[var(--border)] bg-[var(--muted)] text-[var(--muted-fg)]",
};

type Health = "connected" | "degraded" | "down";

function healthOf(status: McpStatus | null): Health {
  if (!status || !status.reachable) return "down";
  if (status.sse_connected === false) return "degraded";
  return "connected";
}

export function McpClient({
  initialStatus,
  initialAgents,
}: {
  initialStatus: McpStatus | null;
  initialAgents: Agent[];
}) {
  const [status, setStatus] = useState<McpStatus | null>(initialStatus);
  const [agents, setAgents] = useState<Agent[]>(initialAgents);
  const [refreshing, setRefreshing] = useState(false);
  const wasReachable = useRef<boolean>(initialStatus?.reachable ?? false);

  const refresh = useCallback(async (manual = false) => {
    setRefreshing(true);
    try {
      const [next, agentsPage] = await Promise.all([
        api.getMcpStatus(),
        api.listAgents().catch(() => null),
      ]);
      setStatus(next);
      if (agentsPage) setAgents(agentsPage.items);
      if (next.reachable !== wasReachable.current) {
        if (next.reachable) toast.success("MCP server is reachable");
        else toast.error(`MCP server is unreachable${next.error ? `: ${next.error}` : ""}`);
        wasReachable.current = next.reachable;
      } else if (manual) {
        toast.success(next.reachable ? "MCP server is reachable" : "MCP server is still down");
      }
    } catch (err) {
      if (manual) toast.error(errorMessage(err, "Failed to reach the backend"));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const id = setInterval(() => void refresh(false), REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const health = healthOf(status);
  const writeTools = (status?.tools ?? []).filter((t) => t.category === "write");
  const readTools = (status?.tools ?? []).filter((t) => t.category === "read");
  const bootstrapTools = (status?.tools ?? []).filter((t) => t.category === "bootstrap");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold tracking-tight">MCP control center</h2>
          <LiveDot health={health} />
        </div>
        <Button size="sm" variant="secondary" onClick={() => void refresh(true)} disabled={refreshing}>
          <RefreshCw className={cn("size-4", refreshing && "animate-spin")} />
          Test connection
        </Button>
      </div>

      <StatusBanner status={status} health={health} />

      <div className="grid gap-4 md:grid-cols-2">
        <ConnectionDetails status={status} />
        <ScreenshotSidecar status={status} />
      </div>

      <OnboardingPrompt status={status} />

      <AgentConnectivity agents={agents} />

      <CommandCatalog
        writeTools={writeTools}
        readTools={readTools}
        bootstrapTools={bootstrapTools}
        reachable={!!status?.reachable}
      />
    </div>
  );
}

function OnboardingPrompt({ status }: { status: McpStatus | null }) {
  const [mcpUrl, setMcpUrl] = useState("");
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    const saved =
      typeof window !== "undefined" ? window.localStorage.getItem(PUBLIC_MCP_URL_LS_KEY) : null;
    const value = saved || withMcpPath(status?.mcp_url);
    if (value) {
      setMcpUrl(value);
      initialized.current = true;
    }
  }, [status?.mcp_url]);

  function update(value: string) {
    setMcpUrl(value);
    try {
      window.localStorage.setItem(PUBLIC_MCP_URL_LS_KEY, value);
    } catch {
      /* ignore quota / unavailable */
    }
  }

  const skillUrl = skillUrlFromMcpUrl(mcpUrl);
  const prompt = buildOnboardingPrompt(
    mcpUrl || "<your pdash MCP URL>",
    skillUrl || "<your pdash skill file URL>",
  );

  async function copySkillUrl() {
    try {
      await navigator.clipboard.writeText(skillUrl || "<your pdash skill file URL>");
      toast.success("Skill file URL copied");
    } catch {
      toast.error("Clipboard unavailable");
    }
  }

  async function copySkillFile() {
    if (!skillUrl) {
      toast.error("Enter the MCP URL first");
      return;
    }
    try {
      const res = await fetch(skillUrl, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await navigator.clipboard.writeText(await res.text());
      toast.success("Skill file copied");
    } catch (err) {
      toast.error(errorMessage(err, "Could not fetch the skill file"));
    }
  }

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(prompt);
      toast.success("Onboarding prompt copied");
    } catch {
      toast.error("Clipboard unavailable");
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2">
        <Sparkles className="size-4 text-[var(--muted-fg)]" />
        <CardTitle>Agent onboarding</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-3 text-sm">
        <p className="text-[var(--muted-fg)]">
          Give a fresh AI agent the hosted skill file first. The copy-paste prompt below stays
          self-contained for agents that cannot fetch it, and still walks through MCP setup,
          registration, and picking up the key once you approve it under{" "}
          <span className="font-medium">Agents</span>. It needs no API key to start — the request
          lands pending for you to approve.
        </p>
        <div className="flex flex-col gap-1">
          <Label>MCP URL (as your agent reaches it)</Label>
          <Input
            value={mcpUrl}
            onChange={(e) => update(e.target.value)}
            placeholder="https://your-host.ts.net/mcp"
            className="font-mono text-xs"
          />
          <p className="text-[11px] text-[var(--muted-fg)]">
            Detected <code className="text-[11px]">{status?.mcp_url ?? "—"}</code> (the backend↔MCP
            address). Edit to the URL your agent actually uses — e.g. your Tailscale address — and
            the prompt updates automatically.
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <Label>Skill file</Label>
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={copySkillUrl}>
                <Copy className="size-4" /> Copy URL
              </Button>
              <Button variant="secondary" size="sm" onClick={() => void copySkillFile()}>
                <Copy className="size-4" /> Copy file
              </Button>
            </div>
          </div>
          <Input
            readOnly
            value={skillUrl || "<your pdash skill file URL>"}
            className="font-mono text-xs"
            onFocus={(e) => e.currentTarget.select()}
          />
          <p className="text-[11px] text-[var(--muted-fg)]">
            This plain <code className="text-[11px]">SKILL.md</code> teaches the model how to add
            pdash as an MCP server before it has any API key.
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <Label>Copy-paste instructions</Label>
            <Button variant="secondary" size="sm" onClick={copyPrompt}>
              <Copy className="size-4" /> Copy instructions
            </Button>
          </div>
          <Textarea
            readOnly
            value={prompt}
            rows={16}
            className="font-mono text-xs"
            onFocus={(e) => e.currentTarget.select()}
          />
        </div>
      </CardBody>
    </Card>
  );
}

function LiveDot({ health }: { health: Health }) {
  const color =
    health === "connected"
      ? "bg-[var(--success)]"
      : health === "degraded"
        ? "bg-[var(--warning)]"
        : "bg-[var(--danger)]";
  return (
    <span className="relative flex size-2" title="Live — auto-refreshing">
      <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping", color)} />
      <span className={cn("relative inline-flex size-2 rounded-full", color)} />
    </span>
  );
}

function StatusBanner({ status, health }: { status: McpStatus | null; health: Health }) {
  const config = {
    connected: { label: "Connected", tone: "success" as const, Icon: Wifi },
    degraded: { label: "Degraded", tone: "warning" as const, Icon: Activity },
    down: { label: "Down", tone: "danger" as const, Icon: WifiOff },
  }[health];
  const { Icon } = config;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-full border",
              TONE_SURFACE[config.tone],
            )}
          >
            <Icon className="size-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold tracking-tight text-[var(--fg)]">
                MCP server
              </span>
              <Badge tone={config.tone}>{config.label}</Badge>
            </div>
            <p className="text-sm text-[var(--muted-fg)]">
              {health === "down"
                ? status?.error ?? "The MCP server is not responding."
                : health === "degraded"
                  ? "Reachable, but not subscribed to the backend event stream."
                  : "Reachable and subscribed to the backend event stream."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <Meta label="MCP" value={status?.mcp_version ? `v${status.mcp_version}` : "—"} />
          <Meta label="Backend" value={status?.backend_version ? `v${status.backend_version}` : "—"} />
        </div>
      </div>
    </Card>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-[var(--muted-fg)]">{label}</span>
      <span className="font-medium text-[var(--fg)]">{value}</span>
    </div>
  );
}

function ConnectionDetails({ status }: { status: McpStatus | null }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2">
        <Plug className="size-4 text-[var(--muted-fg)]" />
        <CardTitle>Connection details</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-2 text-sm">
        <Row label="MCP URL" value={<code className="text-xs">{status?.mcp_url ?? "—"}</code>} />
        <Row
          label="Event stream (SSE)"
          value={
            status?.sse_connected == null ? (
              <Badge tone="neutral">unknown</Badge>
            ) : status.sse_connected ? (
              <Badge tone="success">connected</Badge>
            ) : (
              <Badge tone="warning">disconnected</Badge>
            )
          }
        />
        <Row
          label="Service secret"
          value={
            status?.service_secret_configured ? (
              <Badge tone="success">configured</Badge>
            ) : (
              <Badge tone="danger">missing</Badge>
            )
          }
        />
        <Row
          label="Auth cache TTL"
          value={status?.auth_cache_ttl_s != null ? `${status.auth_cache_ttl_s}s` : "—"}
        />
        <Row
          label="Idempotency window"
          value={status?.idem_dedupe_ttl_s != null ? `${status.idem_dedupe_ttl_s}s` : "—"}
        />
      </CardBody>
    </Card>
  );
}

function ScreenshotSidecar({ status }: { status: McpStatus | null }) {
  const sidecar = status?.screenshot_sidecar;
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2">
        <Camera className="size-4 text-[var(--muted-fg)]" />
        <CardTitle>Screenshot sidecar</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-2 text-sm">
        <Row
          label="Configured"
          value={
            sidecar?.configured ? (
              <Badge tone="success">enabled</Badge>
            ) : (
              <Badge tone="neutral">disabled</Badge>
            )
          }
        />
        <Row
          label="Reachable"
          value={
            !sidecar?.configured ? (
              <span className="text-[var(--muted-fg)]">—</span>
            ) : sidecar.reachable == null ? (
              <Badge tone="neutral">unknown</Badge>
            ) : sidecar.reachable ? (
              <Badge tone="success">reachable</Badge>
            ) : (
              <Badge tone="danger">unreachable</Badge>
            )
          }
        />
        <p className="text-xs text-[var(--muted-fg)]">
          Optional sidecar that renders dashboard pages to PNG for the{" "}
          <code className="text-[11px]">screenshot_page</code> tool.
        </p>
      </CardBody>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[var(--muted-fg)]">{label}</span>
      <span className="text-right text-[var(--fg)]">{value}</span>
    </div>
  );
}

function AgentConnectivity({ agents }: { agents: Agent[] }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Bot className="size-4 text-[var(--muted-fg)]" />
        <h3 className="text-sm font-semibold tracking-tight">Agent connectivity</h3>
      </div>
      {agents.length === 0 ? (
        <EmptyState
          icon={<Bot className="size-12" />}
          title="No agents registered"
          hint="Register an agent on the Agents tab to mint an API key and connect via MCP."
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--border)] bg-[var(--muted)]/60 text-xs font-medium uppercase tracking-wide text-[var(--muted-fg)]">
                <tr>
                  <th className="px-4 py-2 text-left">Agent</th>
                  <th className="px-4 py-2 text-left">Status</th>
                  <th className="px-4 py-2 text-left">Last active</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {agents.map((a) => (
                  <tr key={a.id} className="transition-colors hover:bg-[var(--muted)]/60">
                    <td className="px-4 py-2 font-medium">{a.display_name}</td>
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
                    <td className="px-4 py-2 text-[var(--muted-fg)]">
                      {a.last_active_at ? relativeTime(a.last_active_at) : "never"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function CommandCatalog({
  writeTools,
  readTools,
  bootstrapTools,
  reachable,
}: {
  writeTools: McpTool[];
  readTools: McpTool[];
  bootstrapTools: McpTool[];
  reachable: boolean;
}) {
  const total = writeTools.length + readTools.length + bootstrapTools.length;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Terminal className="size-4 text-[var(--muted-fg)]" />
        <h3 className="text-sm font-semibold tracking-tight">
          Command catalog{total > 0 ? ` (${total})` : ""}
        </h3>
      </div>
      {total === 0 ? (
        <EmptyState
          icon={<Server className="size-12" />}
          title={reachable ? "No commands reported" : "Commands unavailable"}
          hint={
            reachable
              ? "The MCP server returned an empty tool list."
              : "Connect to the MCP server to load its command catalog."
          }
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <ToolGroup
            title="Write commands"
            subtitle="Route through the approval engine"
            tools={writeTools}
            badgeTone="warning"
            badgeLabel="write"
          />
          <ToolGroup
            title="Read commands"
            subtitle="Read-only — no approval needed"
            tools={readTools}
            badgeTone="success"
            badgeLabel="read"
          />
          <ToolGroup
            title="Onboarding commands"
            subtitle="No API key required — for first-time setup"
            tools={bootstrapTools}
            badgeTone="neutral"
            badgeLabel="open"
          />
        </div>
      )}
    </div>
  );
}

function ToolGroup({
  title,
  subtitle,
  tools,
  badgeTone,
  badgeLabel,
}: {
  title: string;
  subtitle: string;
  tools: McpTool[];
  badgeTone: StatusTone;
  badgeLabel: string;
}) {
  if (tools.length === 0) return null;
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="text-xs text-[var(--muted-fg)]">{subtitle}</p>
        </div>
        <Badge tone={badgeTone}>{tools.length}</Badge>
      </CardHeader>
      <ul className="divide-y divide-[var(--border)]">
        {tools.map((t) => (
          <li key={t.name} className="flex flex-col gap-1 px-4 py-3">
            <div className="flex items-center gap-2">
              <code className="font-mono text-sm font-medium text-[var(--fg)]">{t.name}</code>
              <Badge tone={badgeTone} className="text-[10px]">
                {badgeLabel}
              </Badge>
            </div>
            {t.description && (
              <p className="line-clamp-3 text-xs text-[var(--muted-fg)]">{t.description}</p>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
