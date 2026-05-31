import type { ReactNode } from "react";

import { CommandPaletteProvider } from "@/components/layout/CommandPaletteProvider";
import { MobileCommandButton } from "@/components/layout/MobileCommandButton";
import { BottomNav } from "@/components/nav/BottomNav";
import { MobilePagesDrawer } from "@/components/nav/MobilePagesDrawer";
import { Sidebar } from "@/components/nav/Sidebar";
import { api, type Page } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const cookieHeader = await requireSession();
  const { items: pages } = await api.listPages({ cookieHeader });

  return (
    <CommandPaletteProvider>
      <div className="flex min-h-screen">
        <Sidebar pages={pages} />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="md:hidden flex items-center justify-between border-b border-[var(--border)] p-3">
            <MobilePagesDrawer pages={pages} />
            <span className="font-semibold text-sm">Home Base</span>
            <MobileCommandButton />
          </header>
          <main className="flex-1 p-4 pb-20 md:pb-4">{children}</main>
          <BottomNav />
        </div>
      </div>
    </CommandPaletteProvider>
  );
}
