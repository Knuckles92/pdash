import { PagesClient } from "./PagesClient";
import { api, type Page } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

function countDefaultExamples(
  items: { permissions?: Record<string, unknown> }[],
): number {
  return items.filter((m) => m.permissions?.pdash_default_example === true).length;
}

export default async function PagesSettings() {
  const cookieHeader = await requireSession();
  let pages: Page[] = [];
  let initialHomeExampleCount = 0;
  try {
    const res = await api.listPages({ cookieHeader });
    pages = res.items;
    const home = pages.find((p) => p.kind === "home");
    if (home) {
      try {
        const modules = await api.listModules({ page_id: home.id }, { cookieHeader });
        initialHomeExampleCount = countDefaultExamples(modules.items);
      } catch {
        initialHomeExampleCount = 0;
      }
    }
  } catch {
    pages = [];
  }
  return (
    <PagesClient initialPages={pages} initialHomeExampleCount={initialHomeExampleCount} />
  );
}
