import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    // Les envois de photos passent par le relais /api : 10 Mo par défaut, trop peu pour plusieurs
    // photos d'iPhone (elles sont aussi réduites dans le navigateur avant l'envoi).
    middlewareClientMaxBodySize: "100mb",
  },
  // Le navigateur ne parle qu'au frontend : /api est relayé vers le backend (même origine,
  // donc le cookie de session SameSite=Lax fonctionne sans CORS).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
