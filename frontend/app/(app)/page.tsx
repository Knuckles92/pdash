import { notFound } from "next/navigation";

import { loadIframeAllowlistSafe } from "@/components/page/loadIframeAllowlistSafe";
import { PageView } from "@/components/page/PageView";
import { api } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const cookieHeader = await requireSession();
  const { items: pages } = await api.listPages({ cookieHeader });
  const home = pages.find((p) => p.slug === "home");
  if (!home) {
    notFound();
  }
  const { items: modules } = await api.listModules(
    { page_id: home.id },
    { cookieHeader },
  );
  const allowlist = await loadIframeAllowlistSafe(cookieHeader);
  return <PageView page={home} modules={modules} iframeAllowlist={allowlist} />;
}
