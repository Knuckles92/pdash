"use client";

import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/cn";
import type {
  ActionButtonConfig,
  ActionButtonData,
  ActionButtonLastResult,
} from "@/lib/modules/types";
import { relativeTime } from "@/lib/time";

function variantFor(style?: string) {
  switch (style) {
    case "destructive":
      return "danger" as const;
    case "secondary":
      return "secondary" as const;
    case "primary":
    default:
      return "primary" as const;
  }
}

export function ActionButtonModule({
  moduleId,
  data,
  config,
  onFired,
}: {
  moduleId: string;
  data: ActionButtonData;
  config: ActionButtonConfig;
  onFired?: (last_result: ActionButtonLastResult) => void;
}) {
  const [firing, setFiring] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [cooldownLeft, setCooldownLeft] = useState(0);
  const cooldownTimer = useRef<number | null>(null);
  const [localLast, setLocalLast] = useState<ActionButtonLastResult | null>(
    data.last_result ?? null,
  );

  useEffect(() => {
    setLocalLast(data.last_result ?? null);
  }, [data.last_result]);

  useEffect(() => {
    if (cooldownLeft <= 0) return;
    cooldownTimer.current = window.setInterval(() => {
      setCooldownLeft((s) => {
        if (s <= 1) {
          if (cooldownTimer.current) {
            clearInterval(cooldownTimer.current);
            cooldownTimer.current = null;
          }
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => {
      if (cooldownTimer.current) {
        clearInterval(cooldownTimer.current);
        cooldownTimer.current = null;
      }
    };
  }, [cooldownLeft]);

  async function fire() {
    setFiring(true);
    try {
      const res = await api.fireActionButtonModule(moduleId);
      const lastResult: ActionButtonLastResult = {
        fired_at: new Date().toISOString(),
        ok: res.ok,
        message: (res.result?.error as string | undefined) ?? null,
        details: res.result ?? null,
      };
      setLocalLast(lastResult);
      onFired?.(lastResult);
      toast[res.ok ? "success" : "error"](
        res.ok ? "Action fired" : (lastResult.message ?? "Action failed"),
      );
      if (config.cooldown_seconds && config.cooldown_seconds > 0) {
        setCooldownLeft(config.cooldown_seconds);
      }
    } catch (err) {
      toast.error(errorMessage(err, "Failed to fire action"));
    } finally {
      setFiring(false);
    }
  }

  function handleClick() {
    if (config.confirm ?? true) {
      setConfirmOpen(true);
    } else {
      void fire();
    }
  }

  const disabled = !!data.disabled || firing || cooldownLeft > 0;
  const variant = variantFor(config.style);
  const showLastResult = (config.show_last_result ?? true) && localLast;

  return (
    <div className="flex flex-col gap-2">
      <Button
        variant={variant}
        onClick={handleClick}
        disabled={disabled}
        className="w-fit"
      >
        {firing ? (
          <Loader2 className="size-4 animate-spin" />
        ) : null}
        {data.label}
        {cooldownLeft > 0 && (
          <span className="ml-1 text-xs opacity-80">({cooldownLeft}s)</span>
        )}
      </Button>
      {showLastResult && localLast && (
        <div
          className={cn(
            "flex items-start gap-2 text-xs rounded-lg border px-2.5 py-1.5",
            localLast.ok
              ? "border-[var(--success)]/25 bg-[var(--success-soft)] text-[var(--success)]"
              : "border-[var(--danger)]/25 bg-[var(--danger-soft)] text-[var(--danger)]",
          )}
        >
          {localLast.ok ? (
            <CheckCircle2 className="size-3.5 mt-0.5 shrink-0" />
          ) : (
            <XCircle className="size-3.5 mt-0.5 shrink-0" />
          )}
          <div className="min-w-0">
            <span className="font-medium">
              {localLast.ok ? "Succeeded" : "Failed"}
            </span>
            <span className="ml-1 text-[var(--muted-fg)]">
              {relativeTime(localLast.fired_at)}
            </span>
            {localLast.message && (
              <p className="break-words mt-0.5">{localLast.message}</p>
            )}
          </div>
        </div>
      )}

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Confirm action"
        description={
          config.confirm_text ?? "Are you sure you want to fire this action?"
        }
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setConfirmOpen(false)}
              disabled={firing}
            >
              Cancel
            </Button>
            <Button
              variant={variant}
              onClick={async () => {
                setConfirmOpen(false);
                await fire();
              }}
              disabled={firing}
            >
              {firing ? "Firing…" : "Confirm"}
            </Button>
          </>
        }
      >
        <p className="text-sm">{data.label}</p>
      </Dialog>
    </div>
  );
}
