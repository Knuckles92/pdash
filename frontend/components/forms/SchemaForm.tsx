"use client";

import { Plus, Trash2 } from "lucide-react";
import type React from "react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { cn } from "@/lib/cn";

/**
 * Minimal recursive JSON Schema form. Supports the subset emitted by
 * Pydantic for the four Phase-2 module types: object, array, string,
 * number/integer, boolean, enum (anyOf with const), nullable.
 *
 * Not a general JSON-Schema implementation — this is intentional. When more
 * complex modules need it (Phase 4+), swap to @rjsf/core.
 */

export type JSONSchema = {
  type?: string | string[];
  enum?: unknown[];
  anyOf?: JSONSchema[];
  oneOf?: JSONSchema[];
  allOf?: JSONSchema[];
  properties?: Record<string, JSONSchema>;
  required?: string[];
  items?: JSONSchema;
  additionalProperties?: boolean | JSONSchema;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  default?: unknown;
  description?: string;
  title?: string;
  format?: string;
  $ref?: string;
  $defs?: Record<string, JSONSchema>;
  definitions?: Record<string, JSONSchema>;
};

/**
 * Custom widget signature. Matched against the `path` string (e.g.
 * `action_target_id` or `body`). When a widget matches, it replaces the
 * default text/number/enum input entirely. The widget is responsible for
 * rendering its own label.
 */
export type SchemaWidget = (props: {
  value: unknown;
  onChange: (v: unknown) => void;
  label?: string;
  required?: boolean;
}) => React.ReactNode;

export type WidgetMap = Record<string, SchemaWidget>;

type FormProps = {
  schema: JSONSchema;
  value: unknown;
  onChange: (v: unknown) => void;
  rootSchema?: JSONSchema;
  path?: string;
  label?: string;
  required?: boolean;
  widgets?: WidgetMap;
};

function resolveRef(schema: JSONSchema, rootSchema: JSONSchema): JSONSchema {
  if (!schema.$ref) return schema;
  const ref = schema.$ref;
  // E.g. "#/$defs/Severity"
  const segments = ref.replace(/^#\//, "").split("/");
  let node: unknown = rootSchema;
  for (const segment of segments) {
    if (node && typeof node === "object" && segment in (node as Record<string, unknown>)) {
      node = (node as Record<string, unknown>)[segment];
    } else {
      return {};
    }
  }
  return (node as JSONSchema) ?? {};
}

function typeOf(schema: JSONSchema): string {
  if (Array.isArray(schema.type)) {
    return schema.type.find((t) => t !== "null") ?? "string";
  }
  if (schema.type) return schema.type;
  if (schema.enum) return "enum";
  if (schema.properties) return "object";
  if (schema.items) return "array";
  return "string";
}

function defaultFor(schema: JSONSchema): unknown {
  if (schema.default !== undefined) return schema.default;
  const t = typeOf(schema);
  switch (t) {
    case "object":
      return {};
    case "array":
      return [];
    case "boolean":
      return false;
    case "number":
    case "integer":
      return 0;
    default:
      return "";
  }
}

function unwrapAnyOf(schema: JSONSchema): {
  inner: JSONSchema;
  nullable: boolean;
  enumValues?: unknown[];
} {
  const choices = schema.anyOf ?? schema.oneOf;
  if (!choices) return { inner: schema, nullable: false };
  const nonNull = choices.filter((c) => c.type !== "null");
  const nullable = choices.some((c) => c.type === "null");
  // const-style enums: anyOf of { const: x } — also handle enum-on-single-element
  if (nonNull.length === 1 && nonNull[0]) {
    return { inner: nonNull[0], nullable };
  }
  // Pydantic Severity etc. emit allOf or $ref; let the caller resolve.
  return { inner: schema, nullable };
}

function isNullable(schema: JSONSchema): boolean {
  if (Array.isArray(schema.type)) return schema.type.includes("null");
  const choices = schema.anyOf ?? schema.oneOf;
  if (choices && choices.some((c) => c.type === "null")) return true;
  return false;
}

function effectiveSchema(schema: JSONSchema, rootSchema: JSONSchema): JSONSchema {
  let resolved = resolveRef(schema, rootSchema);
  if (resolved.allOf && resolved.allOf.length === 1 && resolved.allOf[0]) {
    // Merge the single allOf base in, but let the local schema's own keys win.
    resolved = { ...resolveRef(resolved.allOf[0], rootSchema), ...resolved, allOf: undefined };
  }
  const { inner } = unwrapAnyOf(resolved);
  if (inner !== resolved) {
    resolved = resolveRef(inner, rootSchema);
  }
  return resolved;
}

export function SchemaForm({
  schema,
  value,
  onChange,
  rootSchema,
  widgets,
}: FormProps) {
  const root = rootSchema ?? schema;
  return (
    <SchemaField
      schema={schema}
      rootSchema={root}
      value={value}
      onChange={onChange}
      path=""
      label={schema.title}
      widgets={widgets}
    />
  );
}

function matchWidget(path: string, widgets?: WidgetMap): SchemaWidget | undefined {
  if (!widgets) return undefined;
  // Match by exact path or by trailing field name (e.g. "action_target_id").
  if (widgets[path]) return widgets[path];
  const last = path.split(/\.|\[\d+\]/).filter(Boolean).pop();
  if (last && widgets[last]) return widgets[last];
  return undefined;
}

/**
 * Props shared by every leaf/branch field component below. `resolvedSchema`
 * is the fully de-referenced schema for this node and `fieldType` its resolved
 * type; the original `schema` is kept around for nullability checks.
 */
type FieldProps = FormProps & {
  resolvedSchema: JSONSchema;
  fieldType: string;
};

function ObjectField({
  schema,
  value,
  onChange,
  rootSchema,
  path = "",
  label,
  widgets,
  resolvedSchema,
}: FieldProps) {
  const root = rootSchema ?? schema;
  const objectValue = (value && typeof value === "object" ? value : {}) as Record<
    string,
    unknown
  >;
  const props = resolvedSchema.properties ?? {};
  const requiredSet = new Set(resolvedSchema.required ?? []);
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[var(--border)] p-3">
      {label && (
        <Label className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted-fg)]/80">
          {label}
        </Label>
      )}
      {Object.entries(props).map(([key, propSchema]) => (
        <SchemaField
          key={key}
          schema={propSchema}
          value={objectValue[key] ?? defaultFor(effectiveSchema(propSchema, root))}
          onChange={(nextValue) => onChange({ ...objectValue, [key]: nextValue })}
          rootSchema={root}
          path={path ? `${path}.${key}` : key}
          label={propSchema.title ?? key}
          required={requiredSet.has(key)}
          widgets={widgets}
        />
      ))}
    </div>
  );
}

function ArrayField({
  schema,
  value,
  onChange,
  rootSchema,
  path = "",
  label,
  required,
  widgets,
  resolvedSchema,
}: FieldProps) {
  const root = rootSchema ?? schema;
  const arrayValue = Array.isArray(value) ? value : [];
  const itemSchema = resolvedSchema.items ?? {};
  // Object items draw their own bordered group; box scalar rows here instead.
  const boxedRows = typeOf(effectiveSchema(itemSchema, root)) !== "object";
  return (
    <div className="flex flex-col gap-2">
      {label && (
        <Label>
          {label}
          {required && <span className="text-[var(--danger)]"> *</span>}
        </Label>
      )}
      <div className="flex flex-col gap-2">
        {arrayValue.map((item, index) => (
          <div
            key={index}
            className={cn(
              "flex items-start gap-2",
              boxedRows && "rounded-lg border border-[var(--border)] p-3",
            )}
          >
            <div className="flex-1">
              <SchemaField
                schema={itemSchema}
                value={item}
                onChange={(nextValue) => {
                  const next = arrayValue.slice();
                  next[index] = nextValue;
                  onChange(next);
                }}
                rootSchema={root}
                path={`${path}[${index}]`}
                label={`#${index + 1}`}
                widgets={widgets}
              />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => onChange(arrayValue.filter((_, otherIndex) => otherIndex !== index))}
              aria-label="Remove item"
              className="mt-1"
            >
              <Trash2 className="size-4 text-[var(--danger)]" />
            </Button>
          </div>
        ))}
      </div>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() =>
          onChange([...arrayValue, defaultFor(effectiveSchema(itemSchema, root))])
        }
        className="w-fit"
      >
        <Plus className="size-3" /> Add item
      </Button>
    </div>
  );
}

function EnumField({ schema, value, onChange, label, required, resolvedSchema }: FieldProps) {
  const options = (resolvedSchema.enum ?? []).map((v) => String(v));
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <Label>
          {label}
          {required && <span className="text-[var(--danger)]"> *</span>}
        </Label>
      )}
      <select
        className={cn(
          "block h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm shadow-[var(--shadow-xs)] transition-[border-color,box-shadow]",
          "hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:border-[var(--accent)] focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]",
        )}
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
      >
        {isNullable(schema) && <option value="">— none —</option>}
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
      {resolvedSchema.description && (
        <p className="text-xs text-[var(--muted-fg)]">{resolvedSchema.description}</p>
      )}
    </div>
  );
}

function BooleanField({ value, onChange, label, required }: FieldProps) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 rounded border-[var(--border-strong)] accent-[var(--accent)] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--accent-soft)]"
      />
      <span>
        {label}
        {required && <span className="text-[var(--danger)]"> *</span>}
      </span>
    </label>
  );
}

function NumberField({
  schema,
  value,
  onChange,
  label,
  required,
  resolvedSchema,
  fieldType,
}: FieldProps) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <Label>
          {label}
          {required && <span className="text-[var(--danger)]"> *</span>}
        </Label>
      )}
      <Input
        type="number"
        value={value === null || value === undefined ? "" : String(value)}
        min={resolvedSchema.minimum}
        max={resolvedSchema.maximum}
        step={fieldType === "integer" ? 1 : "any"}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "") {
            onChange(isNullable(schema) ? null : 0);
            return;
          }
          const n = fieldType === "integer" ? parseInt(raw, 10) : parseFloat(raw);
          onChange(Number.isFinite(n) ? n : 0);
        }}
      />
    </div>
  );
}

function StringField({ value, onChange, path = "", label, required, resolvedSchema }: FieldProps) {
  // String (with format hints)
  const isTextarea =
    (resolvedSchema.maxLength ?? 0) > 200 || path.endsWith(".body") || path === "body";
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <Label>
          {label}
          {required && <span className="text-[var(--danger)]"> *</span>}
        </Label>
      )}
      {isTextarea ? (
        <Textarea
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value)}
          rows={8}
        />
      ) : (
        <Input
          type={resolvedSchema.format === "date-time" ? "datetime-local" : "text"}
          value={value === null || value === undefined ? "" : String(value)}
          maxLength={resolvedSchema.maxLength}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {resolvedSchema.description && (
        <p className="text-xs text-[var(--muted-fg)]">{resolvedSchema.description}</p>
      )}
    </div>
  );
}

/** Resolves the schema/type for a node then delegates to the matching field. */
function SchemaField(props: FormProps) {
  const { schema, value, onChange, rootSchema, path = "", label, required, widgets } = props;
  const root = rootSchema ?? schema;
  const resolvedSchema = effectiveSchema(schema, root);
  const fieldType = resolvedSchema.enum ? "enum" : typeOf(resolvedSchema);

  const widget = matchWidget(path, widgets);
  if (widget) {
    return <>{widget({ value, onChange, label, required })}</>;
  }

  const fieldProps: FieldProps = { ...props, rootSchema: root, resolvedSchema, fieldType };
  switch (fieldType) {
    case "object":
      return <ObjectField {...fieldProps} />;
    case "array":
      return <ArrayField {...fieldProps} />;
    case "enum":
      return <EnumField {...fieldProps} />;
    case "boolean":
      return <BooleanField {...fieldProps} />;
    case "number":
    case "integer":
      return <NumberField {...fieldProps} />;
    default:
      return <StringField {...fieldProps} />;
  }
}

/** Drop null/undefined keys only — keep "", [], and {} so required module fields validate. */
export function pruneEmpties(value: unknown): unknown {
  if (value === null || value === undefined) return value;
  if (Array.isArray(value)) {
    return value.map(pruneEmpties);
  }
  if (typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      const pv = pruneEmpties(v);
      if (pv === null || pv === undefined) continue;
      out[k] = pv;
    }
    return out;
  }
  return value;
}

export function useSchemaFormState<T>(initial: T): { state: T; set: (v: T) => void } {
  const [state, setState] = useState<T>(initial);
  return useMemo(() => ({ state, set: setState }), [state]);
}
