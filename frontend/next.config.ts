import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // Standalone output for Docker/Railway deployment
  output: "standalone",
  // Exclude SSR-incompatible packages from server bundling
  serverExternalPackages: ["react-native"],
  turbopack: {},
};

export default withNextIntl(nextConfig);
