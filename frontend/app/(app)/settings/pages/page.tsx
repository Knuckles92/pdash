import { PagesClient } from "./PagesClient";
import { api, type Page } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function PagesSettings() {
  const cookieHeader = await requireSession();
  let pages: Page[] = [];
  try {
    const res = await api.listPages({ cookieHeader });
    pages = res.items;
  } catch {
    pages = [];
  }
  return <PagesClient initialPages={pages} />;
}
