"use client";

/**
 * Provides the command palette to the whole app:
 *
 * - `⌘K` / `Ctrl+K` toggles the dialog from anywhere.
 * - Exports `useCommandPalette()` for components that want to open it
 *   (e.g. the mobile top-bar palette icon).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { CommandPalette } from "./CommandPalette";

type Ctx = { open: boolean; toggle: () => void; close: () => void };
const CommandPaletteCtx = createContext<Ctx | null>(null);

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((o) => !o), []);

  // Global ⌘K / Ctrl+K.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo(() => ({ open, toggle, close }), [open, toggle, close]);

  return (
    <CommandPaletteCtx.Provider value={value}>
      {children}
      <CommandPalette open={open} onClose={close} />
    </CommandPaletteCtx.Provider>
  );
}

export function useCommandPalette(): Ctx {
  const ctx = useContext(CommandPaletteCtx);
  if (!ctx) {
    // Fallback no-op when used outside the provider (e.g. login page).
    return { open: false, toggle: () => undefined, close: () => undefined };
  }
  return ctx;
}
