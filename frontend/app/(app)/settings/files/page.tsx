import { api, type FilesOverview, type Page } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { FilesClient } from "./FilesClient";

export const dynamic = "force-dynamic";

export default async function FilesSettings() {
  const cookieHeader = await requireSession();
  let overview: FilesOverview | null = null;
  let pages: Page[] = [];
  try {
    overview = await api.listFiles({ cookieHeader });
  } catch {
    overview = null;
  }
  try {
    pages = (await api.listPages({ cookieHeader })).items;
  } catch {
    pages = [];
  }
  return <FilesClient initialOverview={overview} pages={pages} />;
}
