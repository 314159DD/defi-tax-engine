import fs from "fs";
import path from "path";
import matter from "gray-matter";
import readingTime from "reading-time";

export interface BlogPost {
  slug: string;
  title: string;
  description: string;
  date: string;
  tags: string[];
  author: string;
  locale: string;
  readingTime: string;
  content: string;
}

const CONTENT_DIR = path.join(process.cwd(), "content", "blog");

/**
 * Get all blog posts for a given locale, sorted by date (newest first).
 */
export function getAllPosts(locale: string): BlogPost[] {
  const dir = path.join(CONTENT_DIR, locale);
  if (!fs.existsSync(dir)) return [];

  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".mdx"));

  const posts = files.map((filename) => {
    const slug = filename.replace(/\.mdx$/, "");
    return getPostBySlug(slug, locale);
  });

  return posts
    .filter((p): p is BlogPost => p !== null)
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
}

/**
 * Get a single blog post by slug and locale.
 */
export function getPostBySlug(
  slug: string,
  locale: string
): BlogPost | null {
  const filePath = path.join(CONTENT_DIR, locale, `${slug}.mdx`);
  if (!fs.existsSync(filePath)) return null;

  const raw = fs.readFileSync(filePath, "utf-8");
  const { data, content } = matter(raw);
  const stats = readingTime(content);

  return {
    slug,
    title: data.title ?? "",
    description: data.description ?? "",
    date: data.date ?? "",
    tags: Array.isArray(data.tags) ? data.tags : [],
    author: data.author ?? "",
    locale,
    readingTime: stats.text,
    content,
  };
}

/**
 * Get all posts matching a specific tag.
 */
export function getPostsByTag(tag: string, locale: string): BlogPost[] {
  return getAllPosts(locale).filter((post) =>
    post.tags.some((t) => t.toLowerCase() === tag.toLowerCase())
  );
}

/**
 * Get all unique tags across all posts for a locale.
 */
export function getAllTags(locale: string): string[] {
  const posts = getAllPosts(locale);
  const tagSet = new Set<string>();
  for (const post of posts) {
    for (const tag of post.tags) {
      tagSet.add(tag);
    }
  }
  return Array.from(tagSet).sort();
}

/**
 * Extract headings from MDX content for table of contents.
 */
export function extractHeadings(
  content: string
): { level: number; text: string; id: string }[] {
  const headingRegex = /^(#{2,4})\s+(.+)$/gm;
  const headings: { level: number; text: string; id: string }[] = [];
  let match;

  while ((match = headingRegex.exec(content)) !== null) {
    const level = match[1].length;
    const text = match[2].trim();
    const id = text
      .toLowerCase()
      .replace(/[^a-z0-9äöüß]+/g, "-")
      .replace(/(^-|-$)/g, "");
    headings.push({ level, text, id });
  }

  return headings;
}
