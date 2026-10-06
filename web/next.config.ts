import type { NextConfig } from "next";

// Static export: the FastAPI container serves `out/` at "/", so the dashboard and
// the API share one origin. For `next dev` against a separate API, set
// NEXT_PUBLIC_API_URL=http://localhost:8080.
const nextConfig: NextConfig = {
  output: "export",
};

export default nextConfig;
