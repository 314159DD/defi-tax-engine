import { notFound } from "next/navigation";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  COMPETITORS,
  COMPETITOR_SLUGS,
  PRODUCT_NAME,
  OUR_FEATURES,
  OUR_TIERS,
  type CompetitorFeature,
} from "@/data/competitors";

/* Static params for all 5 competitor pages */
export function generateStaticParams() {
  return COMPETITOR_SLUGS.map((competitor) => ({ competitor }));
}

type Props = {
  params: Promise<{ competitor: string; locale: string }>;
};

/* ── Feature status rendering ─────────────────────────────────── */

function StatusIcon({ value }: { value: "yes" | "no" | "partial" | string }) {
  if (value === "yes") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[var(--vault-positive)] font-mono text-sm">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
        Yes
      </span>
    );
  }
  if (value === "no") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[var(--vault-negative)] font-mono text-sm">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
        No
      </span>
    );
  }
  if (value === "partial") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[var(--vault-warning)] font-mono text-sm">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01" />
        </svg>
        Partial
      </span>
    );
  }
  return <span className="font-mono text-sm text-foreground">{value}</span>;
}

/* ── Main page ────────────────────────────────────────────────── */

export default async function ComparisonPage({ params }: Props) {
  const { competitor: slug } = await params;
  const competitor = COMPETITORS[slug];

  if (!competitor) {
    notFound();
  }

  return <ComparisonContent slug={slug} />;
}

function ComparisonContent({ slug }: { slug: string }) {
  const t = useTranslations("compare");
  const competitor = COMPETITORS[slug];

  const featureRows: { key: keyof CompetitorFeature; labelKey: string }[] = [
    { key: "defiAccuracy", labelKey: "featureDeFiAccuracy" },
    { key: "privacy", labelKey: "featurePrivacy" },
    { key: "chains", labelKey: "featureChains" },
    { key: "startingPrice", labelKey: "featurePricing" },
    { key: "reports", labelKey: "featureReports" },
    { key: "cpaTools", labelKey: "featureCpaTools" },
  ];

  const year = new Date().getFullYear();

  return (
    <div className="bg-[var(--vault-bg-deep)] min-h-screen">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

        {/* Back link */}
        <Link
          href="/"
          className="inline-flex items-center gap-2 font-mono text-sm text-[var(--vault-text-tertiary)] hover:text-primary transition-colors mb-12 animate-fade-in-up"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          {t("backToHome")}
        </Link>

        {/* ── HERO - Split feel ──────────────────────────────── */}
        <section className="py-16 md:py-24 animate-fade-in-up delay-1">
          <div className="font-mono text-xs uppercase tracking-widest text-[var(--vault-text-tertiary)] mb-6">
            {year} {t("heroSubtitle")}
          </div>

          <div className="flex flex-col md:flex-row md:items-end gap-4 md:gap-6">
            {/* Competitor name - muted */}
            <h1 className="font-display text-4xl md:text-5xl lg:text-6xl font-bold text-[var(--vault-text-tertiary)] leading-[1.1]">
              {competitor.name}
            </h1>
            {/* vs */}
            <span className="font-mono text-lg md:text-xl text-[var(--vault-text-tertiary)] md:pb-2">
              vs
            </span>
            {/* Our name - amber */}
            <h1 className="font-display text-4xl md:text-5xl lg:text-6xl font-bold text-gradient-amber leading-[1.1]">
              {PRODUCT_NAME}
            </h1>
          </div>

          <p className="font-sans text-[var(--vault-text-secondary)] text-base md:text-lg mt-6 max-w-2xl leading-relaxed">
            {competitor.tagline}
          </p>
        </section>

        <div className="divider-accent mb-16" />

        {/* ── Feature Comparison - Horizontal strips ──────────── */}
        <section className="py-8 animate-fade-in-up delay-2">
          <h2 className="font-display text-2xl md:text-3xl font-bold mb-10">
            {t("featureTableTitle")}
          </h2>

          {/* Column headers */}
          <div className="glass rounded-t-lg px-6 py-3 grid grid-cols-3 gap-4 mb-px">
            <div className="font-mono text-xs uppercase tracking-widest text-[var(--vault-text-tertiary)]">
              {t("featureLabel")}
            </div>
            <div className="text-center font-mono text-xs uppercase tracking-widest text-primary">
              {PRODUCT_NAME}
            </div>
            <div className="text-center font-mono text-xs uppercase tracking-widest text-[var(--vault-text-tertiary)]">
              {competitor.name}
            </div>
          </div>

          {/* Feature rows */}
          <div className="space-y-px">
            {featureRows.map(({ key, labelKey }, i) => (
              <div
                key={key}
                className="glass rounded-none px-6 py-4 grid grid-cols-3 gap-4 items-center last:rounded-b-lg"
              >
                <div className="font-mono text-sm text-foreground">
                  {t(labelKey)}
                </div>
                <div className="text-center">
                  <StatusIcon value={OUR_FEATURES[key]} />
                </div>
                <div className="text-center">
                  <StatusIcon value={competitor.features[key]} />
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── Price Comparison - Side-by-side glass cards ─────── */}
        <section className="py-24 animate-fade-in-up delay-3">
          <h2 className="font-display text-2xl md:text-3xl font-bold mb-10">
            {t("pricingTitle")}
          </h2>

          <div className="grid md:grid-cols-2 gap-6">
            {/* Their pricing */}
            <div className="card-glass p-6">
              <h3 className="font-mono text-sm uppercase tracking-widest text-[var(--vault-text-tertiary)] mb-6">
                {t("pricingTheirTiers", { competitor: competitor.name })}
              </h3>
              <div className="space-y-3">
                {competitor.tiers.map((tier) => (
                  <div
                    key={tier.name}
                    className="flex items-center justify-between py-3 px-4 rounded-md bg-[var(--vault-bg-elevated)]/50"
                  >
                    <div>
                      <span className="font-mono text-sm font-medium text-foreground">{tier.name}</span>
                      <span className="font-mono text-xs text-[var(--vault-text-tertiary)] ml-3">{tier.transactions}</span>
                    </div>
                    <span className="font-data text-sm font-semibold text-[var(--vault-text-secondary)]">{tier.price}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Our pricing */}
            <div className="card-glass-accent p-6">
              <h3 className="font-mono text-sm uppercase tracking-widest text-primary mb-6">
                {t("pricingOurTiers")}
              </h3>
              <div className="space-y-3">
                {OUR_TIERS.map((tier) => (
                  <div
                    key={tier.name}
                    className="flex items-center justify-between py-3 px-4 rounded-md bg-primary/5 border border-primary/15"
                  >
                    <div>
                      <span className="font-mono text-sm font-medium text-foreground">{tier.name}</span>
                      <span className="font-mono text-xs text-[var(--vault-text-tertiary)] ml-3">{tier.transactions}</span>
                    </div>
                    <span className="font-data text-sm font-bold text-primary">{tier.price}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── Why Switch - 3 numbered cards ───────────────────── */}
        <section className="py-24 animate-fade-in-up delay-4">
          <h2 className="font-display text-2xl md:text-3xl font-bold mb-10">
            {t("whySwitchTitle", { product: PRODUCT_NAME })}
          </h2>

          <div className="grid md:grid-cols-3 gap-6">
            {competitor.whySwitch.map((reason, i) => (
              <div key={i} className="card-glass p-6 flex flex-col">
                {/* Amber numbered circle */}
                <div className="w-10 h-10 rounded-full border-2 border-primary bg-primary/10 flex items-center justify-center mb-5">
                  <span className="font-mono text-sm font-bold text-primary">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                </div>
                <p className="font-sans text-sm text-[var(--vault-text-secondary)] leading-relaxed flex-1">
                  {reason}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ── CTA ─────────────────────────────────────────────── */}
        <section className="py-24 animate-fade-in-up delay-5">
          <div className="card-glass-accent p-10 md:p-14 text-center glow-amber rounded-xl">
            <h2 className="font-display text-3xl md:text-4xl font-bold mb-4">
              {t("ctaTitle")}
            </h2>
            <p className="font-sans text-[var(--vault-text-secondary)] text-base md:text-lg mb-8 max-w-xl mx-auto">
              {t("ctaSubtitle")}
            </p>
            <Link href="/estimate" className="btn-primary text-base px-8 py-3">
              {t("ctaButton", { product: PRODUCT_NAME })}
            </Link>
          </div>
        </section>

      </div>
    </div>
  );
}
