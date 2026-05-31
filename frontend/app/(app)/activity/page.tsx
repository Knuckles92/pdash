import { ActivityView } from "@/components/activity/ActivityView";
import {
  api,
  type ActivityLogRow,
  type Agent,
  type Module,
  type Page,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function ActivityPage() {
  const cookieHeader = await requireSession();

  let initialItems: ActivityLogRow[] = [];
  let initialNextCursor: string | null = null;
  let agents: Agent[] = [];
  let pages: Page[] = [];
  let modules: Module[] = [];
  try {
    const [act, agentsRes, pagesRes, modsRes] = await Promise.all([
      api.listActivity({ limit: 50 }, { cookieHeader }),
      api.listAgents({ cookieHeader }),
      api.listPages({ cookieHeader }),
      api.listModules({}, { cookieHeader }),
    ]);
    initialItems = act.items;
    initialNextCursor = act.next_cursor;
    agents = agentsRes.items;
    pages = pagesRes.items;
    modules = modsRes.items;
  } catch {
    /* render empty */
  }

  return (
    <ActivityView
      initialItems={initialItems}
      initialNextCursor={initialNextCursor}
      agents={agents}
      pages={pages}
      modules={modules}
    />
  );
}
