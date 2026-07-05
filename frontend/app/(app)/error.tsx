"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/Button";

function isSessionError(error: Error): boolean {
  const msg = error.message.toLowerCase();
  return (
    msg.includes("session invalid") ||
    msg.includes("authentication required") ||
    msg.includes("not authenticated")
  );
}

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (isSessionError(error)) {
      window.location.replace("/login");
      return;
    }
    console.error(error);
  }, [error]);
  return (
    <div className="rounded-xl border border-[var(--danger)]/25 bg-[var(--danger-soft)] p-5">
      <h2 className="mb-1 text-base font-semibold tracking-tight">Couldn&apos;t load this view</h2>
      <p className="mb-4 text-sm text-[var(--muted-fg)]">{error.message}</p>
      <Button variant="secondary" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
