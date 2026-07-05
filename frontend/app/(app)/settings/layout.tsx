import type { ReactNode } from "react";

import { ConsolePath } from "@/components/layout/ConsolePath";
import { api } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { SettingsTabs } from "./SettingsTabs";

export const dynamic = "force-dynamic";

export default async function SettingsLayout({ children }: { children: ReactNode }) {
  const cookieHeader = await requireSession();
  let version: string | null = null;
  try {
    const about = await api.getAbout({ cookieHeader });
    version = about.version;
  } catch {
    // leave version hidden on fetch failure
  }

  return (
    <div className="flex flex-col gap-4">
      <header>
        <ConsolePath segments={["settings"]} />
        <h1 className="font-display text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--muted-fg)]">
          Manage agents, pages, rules, and integrations.
        </p>
      </header>
      <SettingsTabs />
      <div>{children}</div>
      {version && (
        <footer className="pt-2 text-xs text-[var(--muted-fg)]">
          pdash v{version}
        </footer>
      )}
    </div>
  );
}
