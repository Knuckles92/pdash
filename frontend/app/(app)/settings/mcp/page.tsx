import { McpClient } from "./McpClient";
import { api, type Agent, type McpStatus } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function McpPage() {
  const cookieHeader = await requireSession();

  let status: McpStatus | null = null;
  try {
    status = await api.getMcpStatus({ cookieHeader });
  } catch {
    status = null;
  }

  let agents: Agent[] = [];
  try {
    const res = await api.listAgents({ cookieHeader });
    agents = res.items;
  } catch {
    agents = [];
  }

  return <McpClient initialStatus={status} initialAgents={agents} />;
}
