import { api, type IframeAllowlistEntry } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { IframeAllowlistClient } from "./IframeAllowlistClient";

export const dynamic = "force-dynamic";

export default async function IframeAllowlistSettings() {
  const cookieHeader = await requireSession();
  let entries: IframeAllowlistEntry[] = [];
  try {
    entries = await api.listIframeAllowlist({ cookieHeader });
  } catch {
    entries = [];
  }
  return <IframeAllowlistClient initialEntries={entries} />;
}
