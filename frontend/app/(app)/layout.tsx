import type { ReactNode } from "react";

import { CommandPaletteProvider } from "@/components/layout/CommandPaletteProvider";
import { MobileCommandButton } from "@/components/layout/MobileCommandButton";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { BottomNav } from "@/components/nav/BottomNav";
import { MobilePagesDrawer } from "@/components/nav/MobilePagesDrawer";
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
        <div className="flex min-h-screen">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0">
            <header className="md:hidden sticky top-0 z-40 flex items-center justify-between border-b border-[var(--border)] bg-[var(--bg)]/85 p-3 backdrop-blur">
              <MobilePagesDrawer />
              <span className="font-mono text-sm font-medium">pdash</span>
              <div className="flex items-center">
                <ThemeToggle className="text-[var(--muted-fg)]" />
                <MobileCommandButton />
              </div>
            </header>
            <main className="flex-1 p-4 pb-24 md:p-6 md:pb-8 lg:px-8">
              <div className="mx-auto w-full max-w-[1400px]">{children}</div>
            </main>
            <BottomNav />
          </div>
        </div>
      </PagesProvider>
    </CommandPaletteProvider>
  );
}
