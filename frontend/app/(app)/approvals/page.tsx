import { ApprovalsView } from "@/components/approvals/ApprovalsView";
import { loadIframeAllowlistSafe } from "@/components/page/loadIframeAllowlistSafe";
import {
  api,
  type Agent,
  type ApprovalRequest,
  type IframeAllowlistEntry,
  type Page,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function ApprovalsPage() {
  const cookieHeader = await requireSession();

  let initialRequests: ApprovalRequest[] = [];
  let initialNextCursor: string | null = null;
  let initialTotalPending: number | null = null;
  let agents: Agent[] = [];
  let pages: Page[] = [];
  let iframeAllowlist: IframeAllowlistEntry[] = [];

  try {
    const [reqs, agentsRes, pagesRes, allowlistRes] = await Promise.all([
      api.listApprovalRequests({ status: "pending", limit: 50 }, { cookieHeader }),
      api.listAgents({ cookieHeader }),
      api.listPages({ cookieHeader }),
      loadIframeAllowlistSafe(cookieHeader),
    ]);
    initialRequests = reqs.items;
    initialNextCursor = reqs.next_cursor;
    initialTotalPending = reqs.total_pending;
    agents = agentsRes.items;
    pages = pagesRes.items;
    iframeAllowlist = allowlistRes;
  } catch {
    /* fall through with empty state */
  }

  return (
    <ApprovalsView
      initialRequests={initialRequests}
      initialNextCursor={initialNextCursor}
      initialTotalPending={initialTotalPending}
      agents={agents}
      pages={pages}
      iframeAllowlist={iframeAllowlist}
    />
  );
}
