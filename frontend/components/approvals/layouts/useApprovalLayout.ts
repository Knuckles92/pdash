"use client";

/**
 * The admin's chosen Approvals layout, persisted in localStorage so the choice
 * survives reloads. Default matches the server-rendered initial list (a flat
 * card stack) so the first paint and hydration agree; the stored value is read
 * on mount. Same convention as the theme toggle (`pdash-*` keys).
 */
import { useCallback, useEffect, useState } from "react";

import { DEFAULT_LAYOUT_ID, isLayoutId } from "./index";

const LS_KEY = "pdash-approvals-layout";

export function useApprovalLayout(): [string, (id: string) => void] {
  const [layoutId, setLayoutId] = useState<string>(DEFAULT_LAYOUT_ID);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(LS_KEY);
      if (stored && isLayoutId(stored)) setLayoutId(stored);
    } catch {
      // localStorage unavailable — keep the default.
    }
  }, []);

  const select = useCallback((id: string) => {
    setLayoutId(id);
    try {
      localStorage.setItem(LS_KEY, id);
    } catch {
      // ignore persistence failure; in-memory state still updates.
    }
  }, []);

  return [layoutId, select];
}
