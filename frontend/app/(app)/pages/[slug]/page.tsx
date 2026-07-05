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

export default async function SlugPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const cookieHeader = await requireSession();
  const [page, allowlist] = await Promise.all([
    loadPageBySlug(slug, cookieHeader),
    loadIframeAllowlistSafe(cookieHeader),
  ]);
  if (!page) notFound();
  const { items: modules } = await api.listModules(
    { page_id: page.id },
    { cookieHeader },
  );
  return (
    <PageView
      key={page.id}
      page={page}
      modules={modules}
      iframeAllowlist={allowlist}
    />
  );
}
