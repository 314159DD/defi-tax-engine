import { notFound } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  getAllPosts,
  getPostBySlug,
  extractHeadings,
  type BlogPost,
} from "@/lib/blog";

/* ---------- Static generation ---------- */

export function generateStaticParams() {
  const enPosts = getAllPosts("en");
  const dePosts = getAllPosts("de");
  return [
    ...enPosts.map((p) => ({ locale: "en", slug: p.slug })),
    ...dePosts.map((p) => ({ locale: "de", slug: p.slug })),
  ];
}

/* ---------- SEO Metadata ---------- */

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  const post = getPostBySlug(slug, locale);
  if (!post) return {};

  const url = `https://cryptotax.defi/${locale}/blog/${slug}`;

  return {
    title: `${post.title} | CryptoTax DeFi`,
    description: post.description,
    openGraph: {
      title: post.title,
      description: post.description,
      type: "article",
      url,
      publishedTime: post.date,
      authors: [post.author],
      tags: post.tags,
    },
    alternates: {
      canonical: url,
      languages: {
        en: `/en/blog/${slug}`,
        de: `/de/blog/${slug}`,
      },
    },
  };
}

/* ---------- Page ---------- */

type Props = {
  params: Promise<{ locale: string; slug: string }>;
};

export default async function BlogPostPage({ params }: Props) {
  const { slug } = await params;
  return <BlogPostContent slug={slug} />;
}

/* ---------- Content ---------- */

function BlogPostContent({ slug }: { slug: string }) {
  const locale = useLocale();
  const t = useTranslations("blog");
  const post = getPostBySlug(slug, locale);

  if (!post) {
    notFound();
  }

  const headings = extractHeadings(post.content);
  const relatedPosts = getAllPosts(locale)
    .filter((p) => p.slug !== slug)
    .filter((p) => p.tags.some((tag) => post.tags.includes(tag)))
    .slice(0, 3);

  return (
    <>
      {/* JSON-LD */}
      <ArticleJsonLd post={post} locale={locale} />

      <div className="max-w-6xl mx-auto px-4 py-12 md:py-20">
        <div className="lg:grid lg:grid-cols-[1fr_240px] lg:gap-12">
          {/* Main content */}
          <article className="max-w-3xl animate-fade-in-up">
            {/* Back link */}
            <Link
              href="/blog"
              className="inline-flex items-center gap-2 font-mono text-sm text-muted-foreground hover:text-primary transition-colors mb-8"
            >
              &larr; {t("backToBlog")}
            </Link>

            {/* Header */}
            <header className="mb-10">
              <div className="flex flex-wrap gap-2 mb-4">
                {post.tags.map((tag) => (
                  <span
                    key={tag}
                    className="glass rounded-md px-3 py-1 font-mono text-xs uppercase tracking-wider text-muted-foreground"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight mb-4 leading-[1.1]">
                {post.title}
              </h1>
              <p className="text-lg text-muted-foreground mb-4 leading-relaxed">
                {post.description}
              </p>
              <div className="flex items-center gap-4 font-mono text-sm text-muted-foreground">
                <time dateTime={post.date}>
                  {new Date(post.date).toLocaleDateString(
                    locale === "de" ? "de-DE" : "en-US",
                    { year: "numeric", month: "long", day: "numeric" }
                  )}
                </time>
                <span className="w-1 h-1 rounded-full bg-muted-foreground" />
                <span>{post.readingTime}</span>
                <span className="w-1 h-1 rounded-full bg-muted-foreground" />
                <span>{post.author}</span>
              </div>
              <div className="divider-accent mt-8" />
            </header>

            {/* Article body */}
            <MdxContent content={post.content} />

            {/* CTA */}
            <div className="mt-16 card-glass-accent glow-amber text-center py-10 px-6">
              <h2 className="font-display text-2xl font-bold mb-2">{t("ctaTitle")}</h2>
              <p className="text-muted-foreground mb-6">{t("ctaSubtitle")}</p>
              <Link href="/estimate" className="btn-primary">
                {t("ctaButton")}
              </Link>
            </div>

            {/* Related articles */}
            {relatedPosts.length > 0 && (
              <section className="mt-16">
                <h2 className="font-display text-2xl font-bold mb-6">{t("relatedArticles")}</h2>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {relatedPosts.map((rp) => (
                    <Link key={rp.slug} href={`/blog/${rp.slug}`}>
                      <div className="card-glass h-full group">
                        <h3 className="font-mono text-sm font-semibold mb-2 group-hover:text-primary transition-colors">
                          {rp.title}
                        </h3>
                        <p className="text-sm text-muted-foreground line-clamp-2">
                          {rp.description}
                        </p>
                      </div>
                    </Link>
                  ))}
                </div>
              </section>
            )}
          </article>

          {/* TOC sidebar */}
          {headings.length > 0 && (
            <aside className="hidden lg:block">
              <div className="sticky top-24">
                <div className="glass rounded-lg p-5">
                  <h2 className="font-mono text-xs uppercase tracking-wider text-muted-foreground mb-4">
                    {t("tableOfContents")}
                  </h2>
                  <nav>
                    <ul className="space-y-2">
                      {headings.map((h) => (
                        <li
                          key={h.id}
                          style={{ paddingLeft: `${(h.level - 2) * 12}px` }}
                        >
                          <a
                            href={`#${h.id}`}
                            className="font-mono text-sm text-muted-foreground hover:text-primary transition-colors block py-0.5"
                          >
                            {h.text}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </nav>
                </div>
              </div>
            </aside>
          )}
        </div>
      </div>
    </>
  );
}

/* ---------- MDX Content Renderer ---------- */

function MdxContent({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  function processInline(text: string): React.ReactNode {
    const parts: React.ReactNode[] = [];
    const boldRegex = /\*\*(.+?)\*\*/g;
    let lastIndex = 0;
    let match;

    while ((match = boldRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }
      parts.push(
        <strong key={match.index} className="font-semibold text-foreground">
          {match[1]}
        </strong>
      );
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }
    return parts.length === 1 ? parts[0] : <>{parts}</>;
  }

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("## ")) {
      const text = line.slice(3).trim();
      const id = text
        .toLowerCase()
        .replace(/[^a-z0-9äöüß]+/g, "-")
        .replace(/(^-|-$)/g, "");
      elements.push(
        <h2
          key={i}
          id={id}
          className="font-mono text-2xl font-bold mt-12 mb-4 scroll-mt-24"
        >
          {processInline(text)}
        </h2>
      );
    } else if (line.startsWith("### ")) {
      const text = line.slice(4).trim();
      const id = text
        .toLowerCase()
        .replace(/[^a-z0-9äöüß]+/g, "-")
        .replace(/(^-|-$)/g, "");
      elements.push(
        <h3
          key={i}
          id={id}
          className="font-mono text-xl font-semibold mt-8 mb-3 scroll-mt-24"
        >
          {processInline(text)}
        </h3>
      );
    } else if (line.startsWith("#### ")) {
      const text = line.slice(5).trim();
      elements.push(
        <h4 key={i} className="font-mono text-lg font-semibold mt-6 mb-2">
          {processInline(text)}
        </h4>
      );
    } else if (line.startsWith("- ")) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(
          <li key={i} className="ml-4">
            {processInline(lines[i].slice(2))}
          </li>
        );
        i++;
      }
      elements.push(
        <ul
          key={`ul-${i}`}
          className="list-disc pl-6 space-y-1 my-4 text-muted-foreground leading-relaxed"
        >
          {items}
        </ul>
      );
      continue;
    } else if (/^\d+\.\s/.test(line)) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(
          <li key={i} className="ml-4">
            {processInline(lines[i].replace(/^\d+\.\s/, ""))}
          </li>
        );
        i++;
      }
      elements.push(
        <ol
          key={`ol-${i}`}
          className="list-decimal pl-6 space-y-1 my-4 text-muted-foreground leading-relaxed"
        >
          {items}
        </ol>
      );
      continue;
    } else if (line.trim() === "") {
      // skip blank lines
    } else {
      elements.push(
        <p key={i} className="text-muted-foreground text-base leading-relaxed mb-4">
          {processInline(line)}
        </p>
      );
    }

    i++;
  }

  return <div className="prose-vault">{elements}</div>;
}

/* ---------- JSON-LD Structured Data ---------- */

function ArticleJsonLd({
  post,
  locale,
}: {
  post: BlogPost;
  locale: string;
}) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: post.title,
    description: post.description,
    datePublished: post.date,
    author: {
      "@type": "Organization",
      name: post.author,
    },
    publisher: {
      "@type": "Organization",
      name: "CryptoTax DeFi",
    },
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": `https://cryptotax.defi/${locale}/blog/${post.slug}`,
    },
    inLanguage: locale === "de" ? "de-DE" : "en-US",
    keywords: post.tags.join(", "),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
    />
  );
}
