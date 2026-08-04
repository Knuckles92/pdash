import { notFound } from "next/navigation";

import { loadIframeAllowlistSafe } from "@/components/page/loadIframeAllowlistSafe";
import { PageView } from "@/components/page/PageView";
import { ApiError, api } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

async function loadPageBySlug(slug: string, cookieHeader: string) {
  try {
    return await api.getPageBySlug(slug, { cookieHeader });
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export default async function HomePage() {
  const cookieHeader = await requireSession();
  const [home, allowlist] = await Promise.all([
    loadPageBySlug("home", cookieHeader),
    loadIframeAllowlistSafe(cookieHeader),
  ]);
  if (!home) {
    notFound();
  }
  const { items: modules } = await api.listModules(
    { page_id: home.id },
    { cookieHeader },
  );
  return (
    <PageView
      key={home.id}
      page={home}
      modules={modules}
      iframeAllowlist={allowlist}
    />
  );
}
