"use client";

import { type ReactNode } from "react";

import { Button, type ButtonProps } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";

type ConfirmDialogProps = {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  confirmLabel: ReactNode;
  loadingLabel?: ReactNode;
  cancelLabel?: string;
  confirmVariant?: ButtonProps["variant"];
  loading?: boolean;
  onConfirm: () => void | Promise<void>;
  icon?: ReactNode;
  className?: string;
};

export function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  children,
  confirmLabel,
  loadingLabel,
  cancelLabel = "Cancel",
  confirmVariant = "danger",
  loading = false,
  onConfirm,
  icon,
  className,
}: ConfirmDialogProps) {
  function handleClose() {
    if (!loading) onClose();
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title={title}
      description={description}
      className={className}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={handleClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={confirmVariant}
            onClick={() => void onConfirm()}
            disabled={loading}
          >
            {icon}
            {loading ? (loadingLabel ?? confirmLabel) : confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
