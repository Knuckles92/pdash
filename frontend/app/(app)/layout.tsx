import type { ReactNode } from "react";

import { CommandPaletteProvider } from "@/components/layout/CommandPaletteProvider";
import { BottomNav } from "@/components/nav/BottomNav";
import { MobileAppHeader } from "@/components/nav/MobileAppHeader";
import { PagesProvider } from "@/components/nav/PagesProvider";
import { Sidebar } from "@/components/nav/Sidebar";
import { api } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const cookieHeader = await requireSession();
  const { items: pages } = await api.listPages({ cookieHeader });

  return (
    <CommandPaletteProvider>
      <PagesProvider initialPages={pages}>
        <div className="flex min-h-dvh md:min-h-screen">
          <Sidebar />
          <div className="flex min-h-dvh min-w-0 flex-1 flex-col md:min-h-screen">
            <MobileAppHeader />
            <main className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto p-4 pb-[calc(var(--app-nav-h)+0.75rem)] md:p-6 md:pb-8 lg:px-8">
              <div className="mx-auto w-full max-w-[1400px]">{children}</div>
            </main>
            <BottomNav />
          </div>
        </div>
      </PagesProvider>
    </CommandPaletteProvider>
  );
}
