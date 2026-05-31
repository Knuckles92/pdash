import type { NextConfig } from "next";

const BACKEND_URL = process.env.PDASH_BACKEND_URL ?? "http://localhost:8080";

const nextConfig: NextConfig = {
  // Proxy /api/* to the FastAPI backend in dev so cookies are same-origin.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
  reactStrictMode: true,
  // Phase 6: standalone output produces a minimal runner bundle for Docker.
  output: "standalone",
};

export default nextConfig;
