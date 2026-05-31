export default function NotFound() {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-6 text-center">
      <h2 className="text-lg font-semibold mb-1">Not found</h2>
      <p className="text-sm text-[var(--muted-fg)]">
        That page doesn&apos;t exist (or hasn&apos;t been created yet).
      </p>
    </div>
  );
}
