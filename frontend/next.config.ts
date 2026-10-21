import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // Le navigateur ne parle qu'au frontend : /api est relayé vers le backend (même origine,
  // donc le cookie de session SameSite=Lax fonctionne sans CORS).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
