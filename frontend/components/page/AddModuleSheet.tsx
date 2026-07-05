"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ActionTargetPicker } from "@/components/forms/ActionTargetPicker";
import { FilePicker } from "@/components/forms/FilePicker";
import {
  SchemaForm,
  pruneEmpties,
  type JSONSchema,
  type SchemaWidget,
  type WidgetMap,
} from "@/components/forms/SchemaForm";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Sheet } from "@/components/ui/Sheet";
import { ApiError, api, type Module, type ModuleSchemaEntry } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  MODULE_COLOR_OPTIONS,
  MODULE_THEME_OPTIONS,
  type ModuleAppearanceTheme,
} from "@/lib/modules/appearance";
import { readableTextOn, type ColorToken } from "@/lib/modules/color_token";
import { type Colspan, colspanOf } from "@/lib/modules/grid";
import {
  MODULE_TYPE_DESCRIPTIONS,
  MODULE_TYPE_LABELS,
} from "@/lib/modules/labels";
import {
  ALL_MODULE_TYPES,
  type ModuleType,
} from "@/lib/modules/types";

const WIDTH_OPTIONS: { value: Colspan; label: string }[] = [
  { value: 1, label: "1 column" },
  { value: 2, label: "2 columns" },
  { value: 3, label: "Full width" },
];

type Props = {
  open: boolean;
  onClose: () => void;
  pageId: string;
  nextPosition?: number;
  /** When set, edit instead of create. */
  module?: Module | null;
  onSaved: (m: Module) => void;
};

const DEFAULT_DATA: Record<ModuleType, Record<string, unknown>> = {
  markdown: { body: "" },
  key_value: { fields: [] },
  table: { columns: [], rows: [] },
  link_list: { links: [] },
  timeseries: { series: [] },
  log_stream: { entries: [] },
  iframe: { src: "https://" },
  notification: {
    message: "",
    severity: "info",
    created_at: new Date().toISOString(),
  },
  action_button: { label: "Run", action_target_id: "" },
  file: { file_id: "", kind: "image", display_name: "" },
  sticky_note: { text: "" },
  progress: { bars: [] },
  html: { html: "<!doctype html>\n<html>\n<head></head>\n<body>\n</body>\n</html>" },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseAppearance(value: unknown): {
  theme: ModuleAppearanceTheme;
  color: ColorToken | null;
} {
  const raw = isRecord(value) ? value : {};
  const theme = MODULE_THEME_OPTIONS.some((option) => option.value === raw.theme)
    ? (raw.theme as ModuleAppearanceTheme)
    : "default";
  const color = MODULE_COLOR_OPTIONS.some((option) => option.value === raw.color)
    ? (raw.color as ColorToken)
    : null;
  return { theme, color };
}

function AppearanceWidget({ value, onChange, label }: Parameters<SchemaWidget>[0]) {
  const current = parseAppearance(value);
  const update = (next: { theme?: ModuleAppearanceTheme; color?: ColorToken | null }) => {
    onChange({
      theme: next.theme ?? current.theme,
      color: next.color === undefined ? current.color : next.color,
    });
  };

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-[var(--border)] p-4">
      <Label className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
        {label ?? "Appearance"}
      </Label>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {MODULE_THEME_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() =>
              update({
                theme: option.value,
                color: option.value === "default" ? current.color : current.color ?? "blue",
              })
            }
            className={cn(
              "rounded-lg border px-3 py-2 text-sm transition-colors",
              current.theme === option.value
                ? "border-[var(--accent-border)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--border)] text-[var(--muted-fg)] hover:border-[var(--border-strong)] hover:bg-[var(--muted)]",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-8 gap-2 sm:grid-cols-10">
        <button
          type="button"
          onClick={() => update({ theme: "default", color: null })}
          title="No color"
          aria-label="No color"
          className={cn(
            "relative size-7 rounded-full border transition",
            current.color === null
              ? "border-[var(--fg)] ring-2 ring-[var(--accent-soft)]"
              : "border-[var(--border)] hover:scale-105",
          )}
        >
          <span className="absolute inset-1 rounded-full bg-[linear-gradient(135deg,transparent_44%,var(--danger)_45%,var(--danger)_55%,transparent_56%)]" />
        </button>
        {MODULE_COLOR_OPTIONS.map((option) => {
          const selected = current.color === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => update({ color: option.value })}
              title={option.label}
              aria-label={option.label}
              className={cn(
                "flex size-7 items-center justify-center rounded-full border transition",
                selected
                  ? "border-[var(--fg)] ring-2 ring-[var(--accent-soft)]"
                  : "border-transparent hover:scale-105",
              )}
              style={{
                backgroundColor: option.hex,
                color: readableTextOn(option.value),
              }}
            >
              {selected && <Check className="size-4" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function omitSchemaProperties(
  schema: JSONSchema | null,
  omittedKeys: string[],
): JSONSchema | null {
  if (!schema?.properties) return schema;

  const omitted = new Set(omittedKeys);
  const properties = Object.fromEntries(
    Object.entries(schema.properties).filter(([key]) => !omitted.has(key)),
  );

  if (Object.keys(properties).length === 0) return null;

  return {
    ...schema,
    properties,
    required: schema.required?.filter((key) => !omitted.has(key)),
  };
}

function hasSchemaProperty(schema: JSONSchema | null, key: string): boolean {
  return Boolean(schema?.properties?.[key]);
}

function withoutSchemaTitle(schema: JSONSchema | null): JSONSchema | null {
  return schema ? { ...schema, title: undefined } : null;
}

function countArrayField(
  value: Record<string, unknown>,
  key: string,
  singular: string,
  plural: string,
): string {
  const count = Array.isArray(value[key]) ? value[key].length : 0;
  return `${count} ${count === 1 ? singular : plural}`;
}

function advancedSummary(type: ModuleType | null, data: Record<string, unknown>): string {
  switch (type) {
    case "table":
      return [
        countArrayField(data, "columns", "column", "columns"),
        countArrayField(data, "rows", "row", "rows"),
      ].join(" · ");
    case "key_value":
      return countArrayField(data, "fields", "field", "fields");
    case "link_list":
      return countArrayField(data, "links", "link", "links");
    case "timeseries":
      return countArrayField(data, "series", "series", "series");
    case "log_stream":
      return countArrayField(data, "entries", "entry", "entries");
    case "progress":
      return countArrayField(data, "bars", "bar", "bars");
    case "markdown":
      return data.body ? "Body set" : "Empty body";
    case "iframe":
      return data.src ? "URL set" : "No URL";
    case "notification":
      return data.message ? "Message set" : "No message";
    case "action_button":
      return data.action_target_id ? "Action set" : "No action";
    case "file":
      return data.file_id ? "File set" : "No file";
    default:
      return "Data and settings";
  }
}

// Custom widget overrides — matched by field name. Trailing-field-name match
// means any nested `action_target_id` (e.g. inside `notification.data.action`)
// also gets the picker.
const CUSTOM_WIDGETS: WidgetMap = {
  action_target_id: ActionTargetPicker,
  appearance: AppearanceWidget,
};

export function AddModuleSheet({ open, onClose, pageId, nextPosition, module, onSaved }: Props) {
  const [type, setType] = useState<ModuleType | null>(null);
  const [title, setTitle] = useState("");
  const [schema, setSchema] = useState<ModuleSchemaEntry | null>(null);
  const [data, setData] = useState<Record<string, unknown>>({});
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [width, setWidth] = useState<Colspan>(1);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingSchema, setLoadingSchema] = useState(false);

  // Reset whenever sheet (re)opens
  useEffect(() => {
    if (!open) return;
    if (module) {
      const moduleType = module.type as ModuleType;
      setType(moduleType);
      setTitle(module.title ?? "");
      setData(module.data ?? DEFAULT_DATA[moduleType] ?? {});
      setConfig(module.config ?? {});
      setWidth(colspanOf(module.grid));
      setAdvancedOpen(false);
    } else {
      setType(null);
      setTitle("");
      setData({});
      setConfig({});
      setWidth(1);
      setSchema(null);
      setAdvancedOpen(false);
    }
  }, [open, module]);

  // Load schema whenever type changes
  useEffect(() => {
    if (!type) return;
    let cancelled = false;
    setLoadingSchema(true);
    api
      .getModuleSchema(type)
      .then((s) => {
        if (cancelled) return;
        setSchema(s);
        if (!module) {
          setData((d) =>
            Object.keys(d).length === 0 ? { ...(DEFAULT_DATA[type] ?? {}) } : d,
          );
        }
      })
      .catch((err) => {
        toast.error(
          err instanceof Error ? err.message : "Failed to load module schema",
        );
      })
      .finally(() => {
        if (!cancelled) setLoadingSchema(false);
      });
    return () => {
      cancelled = true;
    };
  }, [type, module]);

  async function handleSave() {
    if (!type) return;
    setSaving(true);
    try {
      const cleanData = pruneEmpties(data) as Record<string, unknown>;
      const cleanConfig = pruneEmpties(config) as Record<string, unknown>;
      // Merge — `grid` is a generic JSON blob; preserve any other keys.
      const grid = { ...(module?.grid ?? {}), colspan: width };
      let saved: Module;
      if (module) {
        saved = await api.patchModule(module.id, {
          title: title || undefined,
          data: cleanData,
          config: cleanConfig,
          grid,
        });
      } else {
        saved = await api.createModule({
          type,
          page_id: pageId,
          title: title || undefined,
          position: nextPosition ?? 0,
          data: cleanData,
          config: cleanConfig,
          grid,
        });
      }
      toast.success(module ? "Module updated" : "Module added");
      onSaved(saved);
      onClose();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? `${err.code}: ${err.message}`
          : err instanceof Error
            ? err.message
            : "Save failed";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  const dataSchema = schema ? ((schema.data_schema ?? schema.data) as JSONSchema) : null;
  const configSchema = schema ? ((schema.config_schema ?? schema.config) as JSONSchema) : null;
  const quickAppearance = hasSchemaProperty(configSchema, "appearance");
  const advancedConfigSchema = omitSchemaProperties(configSchema, ["appearance"]);
  const advancedDataFormSchema = withoutSchemaTitle(dataSchema);
  const advancedConfigFormSchema = withoutSchemaTitle(advancedConfigSchema);
  const showAdvanced = Boolean(dataSchema || advancedConfigSchema);
  // A file widget is useless without a chosen file; gate Save on it.
  const fileReady = type !== "file" || Boolean(data.file_id);

  // Clear the picker back to "no type chosen" (also the per-type seed baseline).
  function resetTypeSelection() {
    setType(null);
    setSchema(null);
    setData({});
    setConfig({});
    setAdvancedOpen(false);
  }

  function selectType(nextType: ModuleType) {
    resetTypeSelection();
    setType(nextType);
    setData({ ...(DEFAULT_DATA[nextType] ?? {}) });
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={module ? "Edit module" : "Add module"}
      description={
        module
          ? "Update the module's data and config."
          : "Pick a type and fill out its data and config."
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || !type || !fileReady}>
            {saving ? "Saving…" : module ? "Save changes" : "Add module"}
          </Button>
        </>
      }
    >
      {!type && !module ? (
        <div className="grid gap-2">
          <Label>Type</Label>
          <div className="grid gap-2">
            {ALL_MODULE_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => selectType(t)}
                className="rounded-lg border border-[var(--border)] p-3 text-left transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--muted)]/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              >
                <div className="font-medium">{MODULE_TYPE_LABELS[t]}</div>
                <div className="text-xs text-[var(--muted-fg)]">
                  {MODULE_TYPE_DESCRIPTIONS[t]}
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              Type:&nbsp;
              <strong>{type ? MODULE_TYPE_LABELS[type] : "—"}</strong>
            </div>
            {!module && (
              <Button variant="ghost" size="sm" onClick={resetTypeSelection}>
                Change
              </Button>
            )}
          </div>
          <div className="flex flex-col gap-1">
            <Label>{type === "table" ? "Table title" : "Title"}</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Optional title shown in the header"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label>Width</Label>
            <div className="flex gap-2">
              {WIDTH_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setWidth(opt.value)}
                  className={cn(
                    "flex-1 rounded-lg border px-3 py-2 text-sm transition-colors",
                    width === opt.value
                      ? "border-[var(--accent-border)] bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "border-[var(--border)] text-[var(--muted-fg)] hover:border-[var(--border-strong)] hover:bg-[var(--muted)]",
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-[var(--muted-fg)]">
              How many dashboard columns this widget occupies on wide screens.
            </p>
          </div>
          {type === "file" && (
            <FilePicker value={data} onChange={(v) => setData(v)} />
          )}
          {quickAppearance && (
            <AppearanceWidget
              value={config.appearance}
              onChange={(v) =>
                setConfig((current) => ({ ...current, appearance: v }))
              }
              label="Appearance"
            />
          )}
          {loadingSchema && (
            <p className="text-sm text-[var(--muted-fg)]">Loading schema…</p>
          )}
          {showAdvanced && (
            <section className="border-t border-[var(--border)] pt-2">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                aria-expanded={advancedOpen}
                onClick={() => setAdvancedOpen((current) => !current)}
              >
                <span className="min-w-0">
                  <span className="block text-sm font-medium">Advanced</span>
                  <span className="block truncate text-xs text-[var(--muted-fg)]">
                    {advancedSummary(type, data)}
                  </span>
                </span>
                <ChevronDown
                  className={cn(
                    "mr-1 size-4 shrink-0 text-[var(--muted-fg)] transition-transform",
                    advancedOpen && "rotate-180",
                  )}
                />
              </button>
              {advancedOpen && (
                <div className="mt-3 flex flex-col gap-4">
                  {advancedDataFormSchema && type !== "file" && (
                    <section>
                      <h3 className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
                        Data
                      </h3>
                      <SchemaForm
                        schema={advancedDataFormSchema}
                        rootSchema={dataSchema ?? advancedDataFormSchema}
                        value={data}
                        onChange={(v) => setData(v as Record<string, unknown>)}
                        widgets={CUSTOM_WIDGETS}
                      />
                    </section>
                  )}
                  {advancedConfigFormSchema && (
                    <section>
                      <h3 className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
                        Settings
                      </h3>
                      <SchemaForm
                        schema={advancedConfigFormSchema}
                        rootSchema={
                          configSchema ?? advancedConfigSchema ?? advancedConfigFormSchema
                        }
                        value={config}
                        onChange={(v) => setConfig(v as Record<string, unknown>)}
                        widgets={CUSTOM_WIDGETS}
                      />
                    </section>
                  )}
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </Sheet>
  );
}
