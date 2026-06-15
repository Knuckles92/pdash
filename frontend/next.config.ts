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
  experimental: {
    // Next 15.5's Segment Explorer devtools panel crashes the React Client
    // Manifest ("Could not find the module …/segment-explorer-node.js#SegmentViewNode"),
    // which forces every Fast Refresh into a full reload and intermittently
    // renders the page with no CSS. Disable it so hot reload works.
    devtoolSegmentExplorer: false,
  },
};

export default nextConfig;
