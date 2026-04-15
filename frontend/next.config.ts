import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    return [
      { source: "/api/query", destination: `${apiUrl}/query` },
      { source: "/api/ingest", destination: `${apiUrl}/ingest` },
      { source: "/api/health", destination: `${apiUrl}/health` },
      { source: "/api/models", destination: `${apiUrl}/models` },
    ];
  },
};

export default nextConfig;
