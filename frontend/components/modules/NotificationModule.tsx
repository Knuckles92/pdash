"use client";

import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/cn";
import { safeHref } from "@/lib/modules/safehref";
import type {
  NotificationConfig,
  NotificationData,
  Severity,
} from "@/lib/modules/types";

const SEV_BORDER: Record<Severity, string> = {
  error: "border-l-red-500",
  warning: "border-l-amber-500",
  success: "border-l-green-500",
  info: "border-l-sky-500",
  muted: "border-l-zinc-400",
};

const SEV_ICON: Record<Severity, LucideIcon> = {
  error: AlertCircle,
  warning: AlertTriangle,
  success: CheckCircle2,
  info: Info,
  muted: Info,
};

const SEV_ICON_COLOR: Record<Severity, string> = {
  error: "text-red-600",
  warning: "text-amber-600",
  success: "text-green-600",
  info: "text-sky-600",
  muted: "text-zinc-500",
};

export function NotificationModule({
  moduleId,
  data,
  config,
  onDismissed,
}: {
  moduleId: string;
  data: NotificationData;
  config: NotificationConfig;
  onDismissed?: () => void;
}) {
  const [dismissedAt, setDismissedAt] = useState<string | null>(
    data.dismissed_at ?? null,
  );
  const [firing, setFiring] = useState(false);

  // Auto-dismiss timer
  useEffect(() => {
    if (!config.auto_dismiss_seconds || dismissedAt) return;
    const ms = config.auto_dismiss_seconds * 1000;
    const t = setTimeout(() => {
      void dismiss();
    }, ms);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.auto_dismiss_seconds, dismissedAt]);

  async function dismiss() {
    if (dismissedAt) return;
    const now = new Date().toISOString();
    setDismissedAt(now);
    try {
      await api.patchModule(moduleId, {
        data: { ...data, dismissed_at: now },
      });
      onDismissed?.();
    } catch (err) {
      // Roll back on failure
      setDismissedAt(null);
      toast.error(errorMessage(err, "Dismiss failed"));
    }
  }

  async function fireAction() {
    const targetId = data.action?.action_target_id;
    if (!targetId) return;
    setFiring(true);
    try {
      const res = await api.testActionTarget(targetId);
      toast[res.ok ? "success" : "error"](res.message);
    } catch (err) {
      toast.error(errorMessage(err, "Failed to fire action"));
    } finally {
      setFiring(false);
    }
  }

  if (dismissedAt) {
    // Hide once dismissed — wrapper handles removing it from the grid.
    return null;
  }

  const Icon = SEV_ICON[data.severity];
  const href = data.action?.href ? safeHref(data.action.href) : null;

  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-md border-l-4 bg-[var(--card)] p-3",
        SEV_BORDER[data.severity],
      )}
    >
      <Icon className={cn("size-5 mt-0.5 shrink-0", SEV_ICON_COLOR[data.severity])} />
      <div className="flex-1 min-w-0">
        <p className="text-sm">{data.message}</p>
        {data.action ? (
          <div className="mt-2">
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-[var(--accent)] hover:underline"
              >
                {data.action.label}
              </a>
            ) : data.action.action_target_id ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={fireAction}
                disabled={firing}
              >
                {firing ? "Running…" : data.action.label}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      {(config.dismissible ?? true) && (
        <Button
          variant="ghost"
          size="icon"
          onClick={dismiss}
          aria-label="Dismiss"
          className="-mr-1"
        >
          <X className="size-4" />
        </Button>
      )}
    </div>
  );
}
