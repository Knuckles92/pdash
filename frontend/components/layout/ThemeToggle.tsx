"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";

type Mode = "system" | "light" | "dark";

function read(): Mode {
  if (typeof window === "undefined") return "system";
  const s = localStorage.getItem("pdash-theme");
  if (s === "light" || s === "dark") return s;
  return "system";
}

function apply(mode: Mode) {
  if (typeof document === "undefined") return;
  if (mode === "system") {
    document.documentElement.removeAttribute("data-theme");
    localStorage.removeItem("pdash-theme");
  } else {
    document.documentElement.setAttribute("data-theme", mode);
    localStorage.setItem("pdash-theme", mode);
  }
}

export function ThemeToggle({ className }: { className?: string }) {
  const [mode, setMode] = useState<Mode>("system");

  useEffect(() => {
    setMode(read());
  }, []);

  const next: Mode = mode === "system" ? "light" : mode === "light" ? "dark" : "system";
  const Icon = mode === "light" ? Sun : mode === "dark" ? Moon : Monitor;
  const label = `Theme: ${mode}`;

  return (
    <Button
      variant="ghost"
      size="icon"
      className={className}
      onClick={() => {
        apply(next);
        setMode(next);
      }}
      title={label}
      aria-label={label}
    >
      <Icon className="size-4" />
    </Button>
  );
}
