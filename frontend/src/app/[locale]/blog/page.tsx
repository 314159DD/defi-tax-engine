import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { getAllPosts, getAllTags } from "@/lib/blog";

export function generateStaticParams() {
  return [{ locale: "en" }, { locale: "de" }];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const isDE = locale === "de";
  return {
    title: isDE
      ? "Blog - Krypto-Steuer-Guides & Neuigkeiten | CryptoTax DeFi"
      : "Blog - Crypto Tax Guides & News | CryptoTax DeFi",
    description: isDE
      ? "Aktuelle Guides zu Krypto-Steuern in Deutschland: Spekulationsfrist, Freigrenze, DeFi-Steuern und mehr."
      : "In-depth guides on crypto taxes: DeFi, 1099-DA, tax loss harvesting, LP positions, and more.",
    alternates: {
      languages: {
        en: "/en/blog",
        de: "/de/blog",
      },
    },
  };
}

export default function BlogListingPage() {
  return <BlogListing />;
}

function BlogListing() {
  const t = useTranslations("blog");
  const locale = useLocale();
  const posts = getAllPosts(locale);
  const tags = getAllTags(locale);

  const featured = posts[0];
  const rest = posts.slice(1);

  return (
    <div className="max-w-5xl mx-auto px-4 py-12 md:py-20">
      {/* Header */}
      <div className="text-center mb-16 animate-fade-in-up">
        <h1 className="font-display text-4xl md:text-5xl font-bold tracking-tight mb-4">
          <span className="text-gradient-amber">{t("title")}</span>
        </h1>
        <p className="text-muted-foreground text-base md:text-lg max-w-xl mx-auto">
          {t("subtitle")}
        </p>
      </div>

      {/* Tag filter pills */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-12 justify-center animate-fade-in-up delay-1">
          <span className="glass rounded-md px-4 py-1.5 font-mono text-xs uppercase tracking-wider text-primary border border-primary/30 cursor-pointer">
            {t("allPosts")}
          </span>
          {tags.map((tag) => (
            <span
              key={tag}
              className="glass rounded-md px-4 py-1.5 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-primary hover:border-primary/30 transition-colors cursor-pointer"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {posts.length === 0 ? (
        <p className="text-center text-muted-foreground font-mono">{t("noPosts")}</p>
      ) : (
        <>
          {/* Featured post */}
          {featured && (
            <Link
              href={`/blog/${featured.slug}`}
              className="block mb-12 animate-fade-in-up delay-2"
            >
              <article className="card-glass-accent p-8 md:p-10 group">
                <div className="flex flex-wrap gap-2 mb-4">
                  {featured.tags.map((tag) => (
                    <span
                      key={tag}
                      className="glass rounded-md px-3 py-1 font-mono text-xs uppercase tracking-wider text-muted-foreground"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
                <h2 className="font-display text-2xl md:text-3xl font-bold mb-3 group-hover:text-primary transition-colors">
                  {featured.title}
                </h2>
                <p className="text-muted-foreground text-base leading-relaxed mb-4 max-w-2xl">
                  {featured.description}
                </p>
                <div className="flex items-center gap-4 font-mono text-xs text-muted-foreground">
                  <time dateTime={featured.date}>
                    {new Date(featured.date).toLocaleDateString(
                      locale === "de" ? "de-DE" : "en-US",
                      { year: "numeric", month: "long", day: "numeric" }
                    )}
                  </time>
                  <span>{featured.readingTime}</span>
                  <span>{featured.author}</span>
                </div>
              </article>
            </Link>
          )}

          {/* Post grid */}
          {rest.length > 0 && (
            <div className="grid md:grid-cols-2 gap-6">
              {rest.map((post, i) => (
                <Link
                  key={post.slug}
                  href={`/blog/${post.slug}`}
                  className={`animate-fade-in-up delay-${Math.min(i + 3, 8)}`}
                >
                  <article className="card-glass h-full group">
                    <div className="flex flex-wrap gap-2 mb-3">
                      {post.tags.map((tag) => (
                        <span
                          key={tag}
                          className="glass rounded-md px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                    <h3 className="font-mono text-base font-semibold mb-2 group-hover:text-primary transition-colors">
                      {post.title}
                    </h3>
                    <p className="text-muted-foreground text-sm leading-relaxed mb-4 line-clamp-2">
                      {post.description}
                    </p>
                    <div className="flex items-center gap-3 font-mono text-xs text-muted-foreground mt-auto">
                      <time dateTime={post.date}>
                        {new Date(post.date).toLocaleDateString(
                          locale === "de" ? "de-DE" : "en-US",
                          { year: "numeric", month: "short", day: "numeric" }
                        )}
                      </time>
                      <span>{post.readingTime}</span>
                    </div>
                  </article>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
