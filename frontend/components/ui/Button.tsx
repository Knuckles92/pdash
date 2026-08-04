"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const buttonStyles = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium select-none transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)] disabled:pointer-events-none disabled:opacity-50 whitespace-nowrap active:scale-[0.98]",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--accent)] text-[var(--accent-fg)] shadow-[var(--shadow-xs)] hover:bg-[var(--accent-hover)]",
        secondary:
          "border border-[var(--border)] bg-[var(--card)] text-[var(--fg)] shadow-[var(--shadow-xs)] hover:border-[var(--border-strong)] hover:bg-[var(--muted)]",
        ghost: "text-[var(--fg)] hover:bg-[var(--muted)]",
        danger:
          "bg-[var(--danger)] text-[var(--danger-fg)] shadow-[var(--shadow-xs)] hover:opacity-90",
        outline:
          "border border-[var(--border-strong)] hover:bg-[var(--muted)]",
      },
      size: {
        sm: "h-8 gap-1.5 px-3 text-[13px]",
        md: "h-9 px-4",
        lg: "h-10 px-5",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonStyles>;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonStyles({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";
