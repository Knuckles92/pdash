"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { useGuideDismissed } from "@/lib/hooks/useGuideDismissed";

export function HelpSettings() {
  const { dismissed, dismiss, restore } = useGuideDismissed();

  return (
    <Card>
      <CardHeader>
        <CardTitle>How it Works</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        <p className="text-sm text-[var(--muted-fg)]">
          A guided tour of pdash — what it is, the approval flow, and the main things you can
          do. Open it anytime, or pin it back to the sidebar.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/how-it-works"
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-4 text-sm font-medium text-[var(--accent-fg)] shadow-[var(--shadow-xs)] transition-colors hover:bg-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]"
          >
            <Sparkles className="size-4" />
            Open the guide
            <ArrowRight className="size-4" />
          </Link>
          {dismissed ? (
            <Button variant="secondary" size="md" onClick={restore}>
              Show in sidebar
            </Button>
          ) : (
            <Button variant="secondary" size="md" onClick={dismiss}>
              Hide from sidebar
            </Button>
          )}
        </div>
        <p className="text-xs text-[var(--muted-fg)]">
          {dismissed
            ? "The guide is currently hidden from the sidebar."
            : "The guide is currently pinned to the sidebar."}
        </p>
      </CardBody>
    </Card>
  );
}
