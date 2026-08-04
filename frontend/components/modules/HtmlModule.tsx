"use client";

import type React from "react";
import { useMemo } from "react";

import { cn } from "@/lib/cn";
import {
  buildHtmlSrcdoc,
  htmlIframeMountKey,
  useEffectiveTheme,
} from "@/lib/modules/html";
import type { HtmlConfig, HtmlData } from "@/lib/modules/types";

// The whole security model: the agent document runs in an opaque origin with
// zero access to the pdash session, storage, or API. Never add
// allow-same-origin — combined with allow-scripts it would collapse the
// sandbox entirely.
const SANDBOX = "allow-scripts allow-popups allow-forms";

/** Inner frame — remounted via `key` whenever html body or theme changes. */
function HtmlIframe({
  srcdoc,
  title,
  className,
  style,
}: {
  srcdoc: string;
  title: string;
  className: string;
  style?: React.CSSProperties;
}) {
  return (
    <iframe
      srcDoc={srcdoc}
      title={title}
      sandbox={SANDBOX}
      referrerPolicy="no-referrer"
      className={className}
      style={style}
    />
  );
}

export function HtmlModule({
  data,
  config,
  fill = false,
}: {
  data: HtmlData;
  config: HtmlConfig;
  /** Canvas pages: fill the parent's height instead of the config heights. */
  fill?: boolean;
}) {
  const theme = useEffectiveTheme();
  const srcdoc = useMemo(
    () => (theme === null ? null : buildHtmlSrcdoc(data.html, theme)),
    [data.html, theme],
  );
  const mountKey = useMemo(
    () => (theme === null ? null : htmlIframeMountKey(data.html, theme)),
    [data.html, theme],
  );
  const heightDesktop = config.height_px ?? 640;
  const heightMobile = config.mobile_height_px ?? 480;

  const frameClass = cn(
    "w-full rounded-lg border border-[var(--border)] bg-[var(--card)]",
    fill ? "h-full" : "h-[var(--html-h-mobile)] md:h-[var(--html-h-desktop)]",
  );
  const frameStyle = fill
    ? undefined
    : ({
        "--html-h-desktop": `${heightDesktop}px`,
        "--html-h-mobile": `${heightMobile}px`,
      } as React.CSSProperties);

  // An iframe must receive its srcdoc exactly once: rewriting the attribute
  // re-navigates the frame, and a re-navigation racing the initial load can
  // leave the frame permanently blank. So: no SSR iframe (the server can't
  // know the theme), mount only once the client theme is read, and remount
  // via key on html+theme changes instead of mutating srcdoc in place.
  if (srcdoc === null || mountKey === null) {
    return <div className={frameClass} style={frameStyle} aria-hidden />;
  }

  return (
    <HtmlIframe
      key={mountKey}
      srcdoc={srcdoc}
      title={data.title ?? "HTML module"}
      className={frameClass}
      style={frameStyle}
    />
  );
}
