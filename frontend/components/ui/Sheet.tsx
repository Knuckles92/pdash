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
    right: "right-0 top-0 h-full w-full max-w-xl border-l",
    left: "left-0 top-0 h-full w-full max-w-xl border-r",
    bottom: "left-0 right-0 bottom-0 h-[85vh] max-h-[85vh] w-full border-t",
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className={cn(
          "absolute flex flex-col bg-[var(--card)] border-[var(--border)] shadow-xl",
          sideClasses[side],
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between p-4 border-b border-[var(--border)]">
          <div>
            {title ? <h2 className="text-lg font-semibold">{title}</h2> : null}
            {description ? (
              <p className="mt-1 text-sm text-[var(--muted-fg)]">{description}</p>
            ) : null}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X className="size-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
        {footer ? (
          <div className="flex items-center justify-end gap-2 p-4 border-t border-[var(--border)]">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}
