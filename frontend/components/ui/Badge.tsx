import { cva, type VariantProps } from "class-variance-authority";
import { type HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const badgeStyles = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      /**
       * Tonal color presets. `none` (default) keeps the badge colorless so
       * callers can fully style it via className.
       */
      tone: {
        none: "",
        neutral: "border-transparent bg-[var(--muted)] text-[var(--muted-fg)]",
        accent: "border-transparent bg-[var(--accent-soft)] text-[var(--accent)]",
        success: "border-transparent bg-[var(--success-soft)] text-[var(--success)]",
        warning: "border-transparent bg-[var(--warning-soft)] text-[var(--warning)]",
        danger: "border-transparent bg-[var(--danger-soft)] text-[var(--danger)]",
        info: "border-transparent bg-[var(--info-soft)] text-[var(--info)]",
        solid: "border-transparent bg-[var(--accent)] text-[var(--accent-fg)]",
      },
    },
    defaultVariants: { tone: "none" },
  },
);

export type BadgeProps = HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeStyles>;

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeStyles({ tone }), className)} {...props} />;
}
