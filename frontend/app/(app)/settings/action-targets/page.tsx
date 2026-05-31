import { api, type ActionTarget } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { ActionTargetsClient } from "./ActionTargetsClient";

export const dynamic = "force-dynamic";

export default async function ActionTargetsSettings() {
  const cookieHeader = await requireSession();
  let targets: ActionTarget[] = [];
  try {
    const res = await api.listActionTargets({ cookieHeader });
    targets = res.items.filter((t) => !t.deleted_at);
  } catch {
    targets = [];
  }
  return <ActionTargetsClient initialTargets={targets} />;
}
