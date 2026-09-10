import type { MetadataRoute } from "next";
import { getAllPosts } from "@/lib/blog";

const BASE_URL = "https://cryptotax.defi";

const STATIC_PAGES = [
  "",
  "/pricing",
  "/estimate",
  "/reconciliation",
  "/blog",
];

const COMPARE_SLUGS = [
  "koinly",
  "cointracker",
  "coinledger",
  "cointracking",
  "blockpit",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const entries: MetadataRoute.Sitemap = [];

  // Static pages for both locales
  for (const locale of ["en", "de"]) {
    for (const page of STATIC_PAGES) {
      entries.push({
        url: `${BASE_URL}/${locale}${page}`,
        lastModified: new Date(),
        changeFrequency: page === "" ? "weekly" : "monthly",
        priority: page === "" ? 1.0 : 0.8,
        alternates: {
          languages: {
            en: `${BASE_URL}/en${page}`,
            de: `${BASE_URL}/de${page}`,
          },
        },
      });
    }

    // Comparison pages
    for (const slug of COMPARE_SLUGS) {
      entries.push({
        url: `${BASE_URL}/${locale}/compare/${slug}`,
        lastModified: new Date(),
        changeFrequency: "monthly",
        priority: 0.7,
        alternates: {
          languages: {
            en: `${BASE_URL}/en/compare/${slug}`,
            de: `${BASE_URL}/de/compare/${slug}`,
          },
        },
      });
    }

    // Blog posts
    const posts = getAllPosts(locale);
    for (const post of posts) {
      entries.push({
        url: `${BASE_URL}/${locale}/blog/${post.slug}`,
        lastModified: new Date(post.date),
        changeFrequency: "monthly",
        priority: 0.6,
        alternates: {
          languages: {
            en: `${BASE_URL}/en/blog/${post.slug}`,
            de: `${BASE_URL}/de/blog/${post.slug}`,
          },
        },
      });
    }
  }

  return entries;
}
