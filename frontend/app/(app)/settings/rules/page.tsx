import { RulesClient } from "./RulesClient";
import {
  api,
  type Agent,
  type ApprovalRule,
  type Page,
} from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

type RulesPageProps = {
  searchParams?: Promise<{ page_id?: string | string[] }>;
};

function firstParam(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}

export default async function RulesPage({ searchParams }: RulesPageProps) {
  const cookieHeader = await requireSession();
  const params = searchParams ? await searchParams : {};
  const pageId = firstParam(params.page_id);
  let rules: ApprovalRule[] = [];
  let agents: Agent[] = [];
  let pages: Page[] = [];
  try {
    const [rs, ag, pg] = await Promise.all([
      api.listApprovalRules(pageId ? { page_id: pageId } : {}, { cookieHeader }),
      api.listAgents({ cookieHeader }),
      api.listPages({ cookieHeader }),
    ]);
    rules = rs.items;
    agents = ag.items;
    pages = pg.items;
  } catch {
    /* empty */
  }
  return (
    <RulesClient
      initialRules={rules}
      agents={agents}
      pages={pages}
      pageId={pageId ?? null}
    />
  );
}
