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
    <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
      <h2 className="text-base font-semibold mb-1">Couldn&apos;t load this view</h2>
      <p className="text-sm text-[var(--muted-fg)] mb-3">{error.message}</p>
      <Button variant="secondary" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
