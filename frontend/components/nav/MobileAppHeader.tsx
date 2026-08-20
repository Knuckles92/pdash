"use client";

import { usePathname } from "next/navigation";

import { MobileCommandButton } from "@/components/layout/MobileCommandButton";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { navTitleFromPath } from "@/lib/navTitle";

import { MobilePagesDrawer } from "./MobilePagesDrawer";
import { usePages } from "./PagesProvider";

/** Sticky phone chrome: pages drawer, current place, theme + search. */
export function MobileAppHeader() {
  const pathname = usePathname() ?? "/";
  const { pages } = usePages();
  const title = navTitleFromPath(pathname, pages);

  return (
    <header className="app-mobile-header md:hidden sticky top-0 z-40 flex items-center gap-1 border-b border-[var(--border)] bg-[var(--bg)]/92 px-1.5 backdrop-blur-md">
      <MobilePagesDrawer />
      <h1 className="min-w-0 flex-1 truncate text-center text-[15px] font-semibold tracking-tight">
        {title}
      </h1>
      <ThemeToggle className="size-11 text-[var(--muted-fg)]" />
      <MobileCommandButton />
    </header>
  );
}
