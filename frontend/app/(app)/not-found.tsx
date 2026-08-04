import { Compass } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--card)]/60 px-6 py-16 text-center">
      <div
        className="mb-2 flex size-12 items-center justify-center rounded-full bg-[var(--muted)] text-[var(--muted-fg)]"
        aria-hidden="true"
      >
        <Compass className="size-5" />
      </div>
      <h2 className="font-medium tracking-tight">Not found</h2>
      <p className="max-w-sm text-sm text-[var(--muted-fg)]">
        That page doesn&apos;t exist (or hasn&apos;t been created yet).
      </p>
    </div>
  );
}
