"use client";

import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

import { cn } from "@/lib/cn";

import { Button } from "./Button";

type SheetSide = "right" | "left" | "bottom";

type SheetProps = {
  open: boolean;
  onClose: () => void;
  side?: SheetSide;
  title?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
};

export function Sheet({
  open,
  onClose,
  side = "right",
  title,
  description,
  children,
  footer,
  className,
}: SheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  const sideClasses: Record<SheetSide, string> = {
    right: "anim-slide-in-right right-0 top-0 h-full w-full max-w-xl border-l rounded-l-2xl",
    left: "anim-slide-in-left left-0 top-0 h-full w-full max-w-xl border-r rounded-r-2xl",
    bottom:
      "anim-slide-in-bottom left-0 right-0 bottom-0 h-[85vh] max-h-[85vh] w-full border-t rounded-t-2xl",
  };

  return (
    <div
      className="anim-overlay-in fixed inset-0 z-50 bg-[var(--overlay)] backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className={cn(
          "absolute flex flex-col border-[var(--border)] bg-[var(--card)] shadow-[var(--shadow-lg)]",
          sideClasses[side],
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] px-5 py-4">
          <div className="min-w-0">
            {title ? (
              <h2 className="text-base font-semibold tracking-tight">{title}</h2>
            ) : null}
            {description ? (
              <p className="mt-1 text-sm text-[var(--muted-fg)]">{description}</p>
            ) : null}
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Close"
            className="-mr-2 -mt-1 shrink-0 text-[var(--muted-fg)]"
          >
            <X className="size-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] bg-[var(--muted)]/50 px-5 py-3.5">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}
