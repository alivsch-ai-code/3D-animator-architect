import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // cacheComponents (Next 16 experimentelles Caching) deaktiviert: alle
  // Projektdaten kommen live vom Backend, Standard-"dynamic"-Rendering
  // (siehe app/page.tsx) ist hier vorhersagbarer als das neue Cache-Modell.
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
