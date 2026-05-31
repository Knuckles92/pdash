"use client";

/** Mobile-only icon button in the top app bar that opens the palette. */

import { Search } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { useCommandPalette } from "./CommandPaletteProvider";

export function MobileCommandButton() {
  const { toggle } = useCommandPalette();
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label="Open command palette"
      className="md:hidden"
    >
      <Search className="size-4" />
    </Button>
  );
}
