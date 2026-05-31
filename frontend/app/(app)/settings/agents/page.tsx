import { AgentsClient } from "./AgentsClient";
import { api, type Agent } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const cookieHeader = await requireSession();
  let agents: Agent[] = [];
  try {
    const res = await api.listAgents({ cookieHeader });
    agents = res.items;
  } catch {
    agents = [];
  }
  return <AgentsClient initialAgents={agents} />;
}
