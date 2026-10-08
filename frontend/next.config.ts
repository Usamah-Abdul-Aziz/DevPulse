import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Produce a self-contained server bundle for the Docker runner stage.
  output: "standalone",
  // Proxy /api to the backend so the frontend works identically locally and on
  // Vercel (where the API is a separate origin). Keeps CORS config minimal.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
