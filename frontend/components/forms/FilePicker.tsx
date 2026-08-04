"use client";

import { FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { api, type RegisteredFile } from "@/lib/api";
import { humanizeBytes } from "@/lib/bytes";
import { cn } from "@/lib/cn";

/**
 * Picks a registered file for a `file` module. Unlike the per-field SchemaForm
 * widgets, this manages the WHOLE file `data` object: selecting a file fills in
 * file_id + kind + mime + size_bytes + display_name in one go (the agent path
 * gets these from register_file; this is the admin's manual equivalent).
 */
export function FilePicker({
  value,
  onChange,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const [files, setFiles] = useState<RegisteredFile[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .listFiles()
      .then((res) => {
        if (!cancelled) setFiles(res.files.filter((f) => f.status === "registered"));
      })
      .catch(() => setFiles([]))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fileId = typeof value.file_id === "string" ? value.file_id : "";
  const displayName = typeof value.display_name === "string" ? value.display_name : "";
  const selected = files.find((f) => f.id === fileId);

  function selectFile(id: string) {
    const f = files.find((x) => x.id === id);
    if (!f) {
      onChange({ ...value, file_id: "" });
      return;
    }
    onChange({
      ...value,
      file_id: f.id,
      kind: f.kind,
      mime: f.mime,
      size_bytes: f.size_bytes,
      display_name: f.display_name,
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <Label>
          File <span className="text-[var(--danger)]">*</span>
        </Label>
        <select
          className={cn(
            "block h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm shadow-[var(--shadow-xs)] transition-[border-color,box-shadow]",
            "hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]",
          )}
          value={fileId}
          onChange={(e) => selectFile(e.target.value)}
        >
          <option value="">{loading ? "Loading…" : "— select a registered file —"}</option>
          {files.map((f) => (
            <option key={f.id} value={f.id}>
              {f.display_name} ({f.kind})
            </option>
          ))}
        </select>
        {!loading && files.length === 0 && (
          <p className="text-xs text-[var(--muted-fg)]">
            No registered files yet. An agent can drop one, or register one in
            Settings → Files.
          </p>
        )}
      </div>

      {selected && (
        <div className="flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--muted)]/40 p-3">
          {selected.kind === "image" ? (
            // eslint-disable-next-line @next/next/no-img-element -- same-origin /api file
            <img
              src={selected.url}
              alt=""
              className="size-12 rounded-md border border-[var(--border)] object-cover shrink-0"
            />
          ) : (
            <FileText className="size-8 text-[var(--muted-fg)] shrink-0" />
          )}
          <div className="min-w-0 text-xs text-[var(--muted-fg)]">
            <p className="truncate">{selected.mime}</p>
            <p>{humanizeBytes(selected.size_bytes)}</p>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <Label>Display name</Label>
        <Input
          value={displayName}
          onChange={(e) => onChange({ ...value, display_name: e.target.value })}
          placeholder="Label shown in the widget"
        />
      </div>
    </div>
  );
}
