"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

export default function ReconciliationPage() {
  const t = useTranslations("reconciliation");

  return (
    <div className="max-w-4xl mx-auto px-4 py-12 md:py-20 space-y-16">
      {/* Hero */}
      <section className="text-center animate-fade-in-up">
        <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight mb-4">
          {t("title")}
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
          {t("subtitle")}
        </p>
      </section>

      {/* Upload Zone */}
      <section className="max-w-2xl mx-auto animate-fade-in-up delay-1">
        <div className="card-glass-accent border-dashed border-primary/50 cursor-pointer hover:border-primary/70 transition-colors">
          <div className="flex flex-col items-center gap-5 py-8">
            {/* Upload icon */}
            <div className="w-16 h-16 rounded-2xl border-2 border-primary/30 flex items-center justify-center">
              <svg
                className="w-8 h-8 text-primary"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
            </div>
            <div className="text-center">
              <p className="font-mono text-lg font-medium">{t("uploadDrag")}</p>
              <p className="text-sm text-muted-foreground mt-1">{t("uploadOr")}</p>
            </div>
            <span className="btn-ghost">{t("uploadBrowse")}</span>
            <p className="font-mono text-xs text-muted-foreground">{t("uploadFormats")}</p>
          </div>
        </div>
      </section>

      {/* What We Check */}
      <section className="animate-fade-in-up delay-2">
        <h2 className="font-display text-2xl font-bold text-center mb-8">{t("checkTitle")}</h2>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
          {/* Card 1 - wider */}
          <div className="md:col-span-5 card-glass">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-full border-2 border-primary bg-[var(--vault-bg-deep)] flex items-center justify-center font-mono text-sm text-primary font-bold shrink-0">
                01
              </div>
              <div>
                <h3 className="font-mono text-base font-semibold mb-1">{t("checkMissingTitle")}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{t("checkMissingDesc")}</p>
              </div>
            </div>
          </div>

          {/* Card 2 */}
          <div className="md:col-span-3 card-glass">
            <div className="w-10 h-10 rounded-full border-2 border-primary bg-[var(--vault-bg-deep)] flex items-center justify-center font-mono text-sm text-primary font-bold mb-3">
              02
            </div>
            <h3 className="font-mono text-base font-semibold mb-1">{t("checkBasisTitle")}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{t("checkBasisDesc")}</p>
          </div>

          {/* Card 3 */}
          <div className="md:col-span-4 card-glass">
            <div className="w-10 h-10 rounded-full border-2 border-primary bg-[var(--vault-bg-deep)] flex items-center justify-center font-mono text-sm text-primary font-bold mb-3">
              03
            </div>
            <h3 className="font-mono text-base font-semibold mb-1">{t("checkDiscrepancyTitle")}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{t("checkDiscrepancyDesc")}</p>
          </div>
        </div>
      </section>

      {/* Why Reconcile */}
      <section className="glass rounded-lg p-8 md:p-10 animate-fade-in-up delay-3">
        <h2 className="font-display text-2xl font-bold mb-3">{t("whyTitle")}</h2>
        <p className="text-muted-foreground leading-relaxed max-w-2xl">
          {t("whyDesc")}
        </p>
      </section>

      {/* CTA */}
      <section className="text-center animate-fade-in-up delay-4">
        <Link href="/dashboard" className="btn-primary text-base px-8 py-3">
          {t("ctaButton")}
        </Link>
      </section>
    </div>
  );
}
