import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/dashboard/", "/wallets/", "/transactions/", "/reports/"],
      },
    ],
    sitemap: "https://cryptotax.defi/sitemap.xml",
  };
}
