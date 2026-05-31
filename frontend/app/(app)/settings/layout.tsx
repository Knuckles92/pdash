import type { ReactNode } from "react";

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
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-[var(--muted-fg)]">
          Manage agents, pages, rules, and integrations.
        </p>
      </header>
      <SettingsTabs />
      <div>{children}</div>
      {version && (
        <footer className="pt-2 text-xs text-[var(--muted-fg)]">
          Home Base v{version}
        </footer>
      )}
    </div>
  );
}
