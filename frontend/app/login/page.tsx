import { LoginForm } from "./LoginForm";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-lg border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
        <h1 className="text-xl font-semibold mb-1">Home Base</h1>
        <p className="text-sm text-[var(--muted-fg)] mb-6">
          Sign in with the admin password.
        </p>
        <LoginForm />
      </div>
    </main>
  );
}
