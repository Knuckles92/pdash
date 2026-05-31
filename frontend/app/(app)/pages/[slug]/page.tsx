import { notFound } from "next/navigation";

import { loadIframeAllowlistSafe } from "@/components/page/loadIframeAllowlistSafe";
import { PageView } from "@/components/page/PageView";
import { api } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function SlugPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const cookieHeader = await requireSession();
  const { items: pages } = await api.listPages({ cookieHeader });
  const page = pages.find((p) => p.slug === slug);
  if (!page) notFound();
  const { items: modules } = await api.listModules(
    { page_id: page.id },
    { cookieHeader },
  );
  const allowlist = await loadIframeAllowlistSafe(cookieHeader);
  return <PageView page={page} modules={modules} iframeAllowlist={allowlist} />;
}
