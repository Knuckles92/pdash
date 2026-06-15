"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type {
  AnchorHTMLAttributes,
  FocusEvent,
  MouseEvent,
  ReactNode,
  TouchEvent,
} from "react";

type NavigateEvent = { preventDefault: () => void };

type WarmLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  children: ReactNode;
  onNavigate?: (event: NavigateEvent) => void;
  prefetch?: boolean;
};

export function WarmLink({
  href,
  children,
  onFocus,
  onMouseEnter,
  onTouchStart,
  prefetch = true,
  ...props
}: WarmLinkProps) {
  const router = useRouter();

  function warmRoute() {
    if (href.startsWith("/")) {
      try {
        router.prefetch(href);
      } catch {
        /* prefetch is opportunistic */
      }
    }
  }

  return (
    <Link
      href={href}
      prefetch={prefetch}
      onFocus={(event: FocusEvent<HTMLAnchorElement>) => {
        warmRoute();
        onFocus?.(event);
      }}
      onMouseEnter={(event: MouseEvent<HTMLAnchorElement>) => {
        warmRoute();
        onMouseEnter?.(event);
      }}
      onTouchStart={(event: TouchEvent<HTMLAnchorElement>) => {
        warmRoute();
        onTouchStart?.(event);
      }}
      {...props}
    >
      {children}
    </Link>
  );
}
