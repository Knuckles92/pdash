import { LayoutDashboard } from "lucide-react";

import { LoginForm } from "./LoginForm";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      {/* Soft accent glow behind the card. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-[-30%] mx-auto h-[60vh] w-[60vw] rounded-full bg-[var(--accent)] opacity-[0.07] blur-3xl"
      />
      <div className="anim-fade-up relative w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--card)] p-8 shadow-[var(--shadow-md)]">
        <div className="mb-6 flex flex-col items-start gap-3">
          <span className="flex size-10 items-center justify-center rounded-xl bg-[var(--accent)] text-[var(--accent-fg)] shadow-[var(--shadow-sm)]">
            <LayoutDashboard className="size-5" />
          </span>
          <div>
            <h1 className="font-mono text-lg font-medium tracking-tight">
              pdash
              <span aria-hidden="true" className="anim-caret ml-0.5 text-[var(--accent)]">
                _
              </span>
            </h1>
            <p className="mt-0.5 text-sm text-[var(--muted-fg)]">
              Sign in with the admin password.
            </p>
          </div>
        </div>
        <LoginForm />
      </div>
    </main>
  );
}
