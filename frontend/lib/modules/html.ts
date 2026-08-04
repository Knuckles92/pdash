"use client";

import { useSyncExternalStore } from "react";

/**
 * srcdoc builder for the html module: injects pdash design tokens into the
 * agent's document so it can render on-theme inside its sandboxed iframe
 * (opaque origin — parent CSS, fonts, and variables don't reach it).
 *
 * Token values mirror frontend/app/globals.css (source of truth — keep in
 * sync). Exposed under a --pdash- prefix to avoid colliding with variables
 * the agent defines. The contract is documented for agents in
 * backend/app/modules/html.py (_HTML_DESC).
 */
const TOKEN_STYLE = `<style data-pdash-tokens>
:root {
  color-scheme: __SCHEME__;
  --pdash-bg: light-dark(#f6f7f9, #101216);
  --pdash-fg: light-dark(#1a1d23, #e9ebef);
  --pdash-muted: light-dark(#eef0f3, #1d2129);
  --pdash-muted-fg: light-dark(#5d6572, #99a1b0);
  --pdash-border: light-dark(#e4e7ec, #272c36);
  --pdash-card: light-dark(#ffffff, #171a20);
  --pdash-accent: light-dark(#47698c, #8fb3d6);
  --pdash-accent-fg: light-dark(#ffffff, #0e1015);
  --pdash-accent-soft: light-dark(rgba(71, 105, 140, 0.1), rgba(143, 179, 214, 0.14));
  --pdash-danger: light-dark(#dc2626, #f0645f);
  --pdash-warning: light-dark(#b45309, #f5b04d);
  --pdash-success: light-dark(#16803c, #57c58a);
  --pdash-info: light-dark(#0270ad, #58b9f0);
  --pdash-font-sans: "IBM Plex Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --pdash-font-display: var(--pdash-font-sans);
  --pdash-font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", SFMono-Regular, Menlo, monospace;
}
</style>`;

export type EffectiveTheme = "light" | "dark";

/** Stable mount key for html iframes — any body or theme change must remount. */
export function htmlIframeMountKey(html: string, theme: EffectiveTheme): string {
  return `${theme}:${hashString(html)}`;
}

function hashString(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h) ^ s.charCodeAt(i);
  }
  return (h >>> 0).toString(36);
}

/**
 * Insert the token style block into the document without breaking parsing:
 * after <head>, else after <html>, else after <!doctype>, else prepend.
 * (Prepending before a doctype would void it and trigger quirks mode.)
 */
export function buildHtmlSrcdoc(html: string, theme: EffectiveTheme): string {
  const block = TOKEN_STYLE.replace("__SCHEME__", theme);
  for (const re of [/<head[^>]*>/i, /<html[^>]*>/i, /<!doctype[^>]*>/i]) {
    const m = re.exec(html);
    if (m) {
      const i = m.index + m[0].length;
      return html.slice(0, i) + block + html.slice(i);
    }
  }
  return block + html;
}

function subscribeToTheme(notify: () => void): () => void {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const observer = new MutationObserver(notify);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  mq.addEventListener("change", notify);
  return () => {
    observer.disconnect();
    mq.removeEventListener("change", notify);
  };
}

function readEffectiveTheme(): EffectiveTheme {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark") return "dark";
  if (attr === "light") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * The app has no theme context: the active theme is `data-theme` on <html>
 * (set pre-paint by ThemeScript; absent = follow the OS). Reads synchronously
 * so the first client render already has the real theme, and returns null on
 * the server/hydration pass — consumers must not guess a theme there (see
 * HtmlModule: an srcdoc rendered with a guessed theme gets rewritten after
 * hydration, and re-navigating an iframe mid-load can leave it blank).
 */
export function useEffectiveTheme(): EffectiveTheme | null {
  return useSyncExternalStore(subscribeToTheme, readEffectiveTheme, () => null);
}
