import { Toaster } from "sonner";
import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";

import { RealtimeProvider } from "@/components/layout/RealtimeProvider";
import { ThemeScript } from "@/components/layout/ThemeScript";

import "./globals.css";

// Self-hosted (Tailscale-only deployment — no external font CDNs).
// Inter carries body/UI text; IBM Plex Sans and Plex Mono are the display and
// machine voices (see the font tokens in globals.css).
const inter = localFont({
  src: "./fonts/inter-latin-wght-normal.woff2",
  variable: "--font-inter",
  display: "swap",
  weight: "100 900",
});

const plexSans = localFont({
  src: "./fonts/ibm-plex-sans-latin-600-normal.woff2",
  variable: "--font-plex-sans",
  display: "swap",
  weight: "600",
});

const plexMono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-latin-400-normal.woff2", weight: "400" },
    { path: "./fonts/ibm-plex-mono-latin-500-normal.woff2", weight: "500" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "pdash",
  description: "Self-hosted command center",
};

export const dynamic = "force-dynamic";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${plexSans.variable} ${plexMono.variable}`}
    >
      <head>
        <ThemeScript />
      </head>
      <body className="min-h-screen font-sans antialiased">
        <RealtimeProvider>
          {children}
          <Toaster richColors closeButton position="bottom-right" />
        </RealtimeProvider>
      </body>
    </html>
  );
}
