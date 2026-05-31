import { Toaster } from "sonner";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { RealtimeProvider } from "@/components/layout/RealtimeProvider";
import { ThemeScript } from "@/components/layout/ThemeScript";

import "./globals.css";

export const metadata: Metadata = {
  title: "Home Base",
  description: "Self-hosted command center",
};

export const dynamic = "force-dynamic";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body className="min-h-screen">
        <RealtimeProvider>
          {children}
          <Toaster richColors closeButton position="bottom-right" />
        </RealtimeProvider>
      </body>
    </html>
  );
}
