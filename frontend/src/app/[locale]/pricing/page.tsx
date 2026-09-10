"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import { billing, type TierLimits } from "@/lib/api";

const TIER_KEYS = ["free", "pro", "unlimited"] as const;

const FEATURE_KEYS = [
  "wallets",
  "chains",
  "transactions",
  "methods",
  "harvestSuggestions",
  "prioritySupport",
  "cpaExport",
  "reconciliation",
] as const;

export default function PricingPage() {
  const t = useTranslations("pricing");
  const tc = useTranslations("common");
  const locale = useLocale();
  const isDE = locale === "de";

  const [tiers, setTiers] = useState<Record<string, TierLimits> | null>(null);
  const [interval, setInterval] = useState<"monthly" | "annual">("monthly");
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    billing.tiers().then(setTiers);
  }, []);

  const handleUpgrade = async (tier: string) => {
    if (tier === "free") return;
    setLoading(tier);
    try {
      const { url } = await billing.checkout(tier, interval);
      window.location.href = url;
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  };

  /* ---------- DE: per-Steuerjahr pricing ---------- */
  const dePricing: Record<string, { price: string; label: string }> = {
    free: { price: "€0", label: t("tierFree") },
    pro: { price: "€49", label: t("deTierStandard") },
    unlimited: { price: "€179", label: t("deTierUnlimited") },
  };

  /* ---------- US: monthly pricing ---------- */
  const usPricing: Record<string, { monthly: string; annual: string; label: string }> = {
    free: { monthly: "$0", annual: "$0", label: t("tierFree") },
    pro: { monthly: "$9.99", annual: "$99", label: t("tierPro") },
    unlimited: { monthly: "$29.99", annual: "$299", label: t("tierUnlimited") },
  };

  const getPrice = (tier: string) => {
    if (isDE) return dePricing[tier]?.price ?? "-";
    const p = usPricing[tier];
    return interval === "monthly" ? p?.monthly ?? "-" : p?.annual ?? "-";
  };

  const getTierLabel = (tier: string) => {
    if (isDE) return dePricing[tier]?.label ?? tier;
    return usPricing[tier]?.label ?? tier;
  };

  const getPriceSuffix = (tier: string) => {
    if (tier === "free") return "";
    if (isDE) return tc("perTaxYear");
    return interval === "monthly" ? tc("perMonth") : tc("perYear");
  };

  /* Feature data per tier */
  const featureData: Record<string, Record<string, string | boolean>> = {
    free: {
      wallets: "1",
      chains: t("featureFreeChain"),
      transactions: "100",
      methods: "FIFO",
      harvestSuggestions: false as unknown as string,
      prioritySupport: false as unknown as string,
      cpaExport: false as unknown as string,
      reconciliation: false as unknown as string,
    },
    pro: {
      wallets: "5",
      chains: t("featureAllChains"),
      transactions: "5,000",
      methods: "FIFO / LIFO / HIFO",
      harvestSuggestions: true as unknown as string,
      prioritySupport: false as unknown as string,
      cpaExport: false as unknown as string,
      reconciliation: true as unknown as string,
    },
    unlimited: {
      wallets: tc("unlimited"),
      chains: t("featureAllChains"),
      transactions: tc("unlimited"),
      methods: "FIFO / LIFO / HIFO",
      harvestSuggestions: true as unknown as string,
      prioritySupport: true as unknown as string,
      cpaExport: true as unknown as string,
      reconciliation: true as unknown as string,
    },
  };

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="py-24 md:py-32">
        <div className="max-w-5xl mx-auto px-6 text-center">
          <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl tracking-tight text-gradient-amber animate-fade-in-up">
            {t("title")}
          </h1>
          <p className="mt-6 text-lg text-[var(--vault-text-secondary)] max-w-2xl mx-auto animate-fade-in-up delay-1">
            {t("subtitle")}
          </p>

          {/* Interval toggle - US only */}
          {!isDE && (
            <div className="flex justify-center gap-1 mt-8 animate-fade-in-up delay-2">
              <div className="glass rounded-lg p-1 inline-flex">
                {(["monthly", "annual"] as const).map((i) => (
                  <button
                    key={i}
                    onClick={() => setInterval(i)}
                    className={`font-mono text-sm px-5 py-2 rounded-md transition-all duration-200 ${
                      interval === i
                        ? "bg-primary text-primary-foreground"
                        : "text-[var(--vault-text-secondary)] hover:text-foreground"
                    }`}
                  >
                    {tc(i)}
                    {i === "annual" && (
                      <span className="ml-2 text-xs opacity-70">{tc("save17")}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* DE: per-Steuerjahr note */}
          {isDE && (
            <p className="mt-6 font-mono text-sm text-primary animate-fade-in-up delay-2">
              {t("dePerTaxYear")}
            </p>
          )}
        </div>
      </section>

      {/* Pricing Cards - Asymmetric */}
      <section className="pb-24 md:pb-32">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid lg:grid-cols-12 gap-6 items-start animate-fade-in-up delay-3">
            {/* Free - compact left */}
            <div className="lg:col-span-3">
              <div className="card-glass p-6 h-full">
                <p className="font-mono text-xs uppercase tracking-wider text-[var(--vault-text-tertiary)] mb-4">
                  {getTierLabel("free")}
                </p>
                <div className="mb-6">
                  <span className="font-mono text-3xl font-bold text-foreground">{getPrice("free")}</span>
                </div>
                <ul className="space-y-3 mb-8">
                  {["freeFeature1", "freeFeature2", "freeFeature3"].map((k) => (
                    <li key={k} className="flex items-start gap-2 text-sm text-[var(--vault-text-secondary)]">
                      <span className="text-[var(--vault-text-tertiary)] mt-0.5">--</span>
                      <span>{t(k)}</span>
                    </li>
                  ))}
                </ul>
                <button className="btn-ghost w-full" disabled>
                  {tc("currentPlan")}
                </button>
              </div>
            </div>

            {/* Pro - prominent center */}
            <div className="lg:col-span-6">
              <div className="card-glass-accent glow-amber relative overflow-hidden">
                {/* Amber top border */}
                <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-primary to-transparent" />

                {/* Popular badge */}
                <div className="absolute top-4 right-4">
                  <span className="font-mono text-[10px] uppercase tracking-widest bg-primary text-primary-foreground px-3 py-1 rounded-full">
                    {t("mostPopular")}
                  </span>
                </div>

                <div className="p-8 md:p-10">
                  <p className="font-mono text-xs uppercase tracking-wider text-primary mb-4">
                    {getTierLabel("pro")}
                  </p>
                  <div className="mb-2">
                    <span className="font-mono text-5xl md:text-6xl font-bold text-foreground">
                      {getPrice("pro")}
                    </span>
                    <span className="font-mono text-lg text-[var(--vault-text-secondary)] ml-1">
                      {getPriceSuffix("pro")}
                    </span>
                  </div>
                  {isDE && (
                    <p className="text-sm text-[var(--vault-text-tertiary)] mb-6">{t("deProSubline")}</p>
                  )}

                  <div className="divider-accent my-6" />

                  <ul className="space-y-3 mb-8">
                    {["proFeature1", "proFeature2", "proFeature3", "proFeature4", "proFeature5"].map((k) => (
                      <li key={k} className="flex items-start gap-3 text-sm">
                        <span className="text-primary font-mono mt-0.5 shrink-0">{"//"}</span>
                        <span className="text-foreground">{t(k)}</span>
                      </li>
                    ))}
                  </ul>

                  <button
                    className="btn-primary w-full text-base py-3"
                    onClick={() => handleUpgrade("pro")}
                    disabled={loading === "pro"}
                  >
                    {loading === "pro" ? tc("redirecting") : t("upgradeToTier", { tier: getTierLabel("pro") })}
                  </button>
                </div>
              </div>
            </div>

            {/* Unlimited - compact right */}
            <div className="lg:col-span-3">
              <div className="card-glass p-6 h-full">
                <p className="font-mono text-xs uppercase tracking-wider text-[var(--vault-text-tertiary)] mb-4">
                  {getTierLabel("unlimited")}
                </p>
                <div className="mb-2">
                  <span className="font-mono text-3xl font-bold text-foreground">{getPrice("unlimited")}</span>
                  <span className="font-mono text-sm text-[var(--vault-text-secondary)] ml-1">
                    {getPriceSuffix("unlimited")}
                  </span>
                </div>
                <ul className="space-y-3 mb-8 mt-6">
                  {["unlimitedFeature1", "unlimitedFeature2", "unlimitedFeature3"].map((k) => (
                    <li key={k} className="flex items-start gap-2 text-sm text-[var(--vault-text-secondary)]">
                      <span className="text-primary mt-0.5 shrink-0 font-mono">&gt;</span>
                      <span>{t(k)}</span>
                    </li>
                  ))}
                </ul>
                <button
                  className="btn-accent w-full"
                  onClick={() => handleUpgrade("unlimited")}
                  disabled={loading === "unlimited"}
                >
                  {loading === "unlimited" ? tc("redirecting") : t("upgradeToTier", { tier: getTierLabel("unlimited") })}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Comparison Table */}
      <section className="py-24 md:py-32">
        <div className="max-w-5xl mx-auto px-6">
          <h2 className="font-display text-2xl md:text-3xl text-center mb-12 animate-fade-in-up">
            {t("compareTitle")}
          </h2>

          <div className="glass rounded-xl overflow-hidden animate-fade-in-up delay-1">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/[0.06]">
                    <th className="text-left py-4 px-6 font-mono text-xs uppercase tracking-wider text-[var(--vault-text-tertiary)]">
                      {t("featureLabel")}
                    </th>
                    {TIER_KEYS.map((tier) => (
                      <th
                        key={tier}
                        className={`text-center py-4 px-6 font-mono text-xs uppercase tracking-wider ${
                          tier === "pro" ? "text-primary" : "text-[var(--vault-text-tertiary)]"
                        }`}
                      >
                        {getTierLabel(tier)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {FEATURE_KEYS.map((feat, i) => (
                    <tr
                      key={feat}
                      className={`border-b border-white/[0.04] ${i % 2 === 0 ? "" : "bg-white/[0.02]"}`}
                    >
                      <td className="py-3.5 px-6 font-mono text-sm text-[var(--vault-text-secondary)]">
                        {t(`feature_${feat}`)}
                      </td>
                      {TIER_KEYS.map((tier) => {
                        const val = featureData[tier]?.[feat];
                        const isBoolean = typeof val === "boolean";
                        return (
                          <td key={tier} className="text-center py-3.5 px-6">
                            {isBoolean ? (
                              val ? (
                                <span className="text-primary font-mono text-sm">{"//"}</span>
                              ) : (
                                <span className="text-[var(--vault-text-tertiary)]">--</span>
                              )
                            ) : (
                              <span className={`font-mono text-sm ${tier === "pro" ? "text-foreground" : "text-[var(--vault-text-secondary)]"}`}>
                                {val}
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      {/* Steuerberater / CPA Section */}
      <section className="py-24 md:py-32">
        <div className="max-w-5xl mx-auto px-6">
          <div className="glass rounded-xl p-8 md:p-12 animate-fade-in-up">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-8">
              <div className="flex-1">
                <p className="font-mono text-xs uppercase tracking-wider text-primary mb-3">
                  {isDE ? t("steuerberaterBadge") : t("cpaBadge")}
                </p>
                <h2 className="font-display text-2xl md:text-3xl mb-3">
                  {isDE ? t("steuerberaterTitle") : t("cpaTitle")}
                </h2>
                <p className="text-[var(--vault-text-secondary)] leading-relaxed max-w-xl">
                  {isDE ? t("steuerberaterDesc") : t("cpaDesc")}
                </p>
              </div>
              <div className="shrink-0">
                <Link href="/estimate">
                  <button className="btn-primary whitespace-nowrap">
                    {isDE ? t("steuerberaterCta") : t("cpaCta")}
                  </button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Privacy note */}
      <section className="pb-24 md:pb-32">
        <div className="max-w-3xl mx-auto px-6 text-center">
          <p className="font-mono text-xs text-[var(--vault-text-tertiary)] leading-relaxed">
            {t("privacyNote")}
          </p>
          <p className="mt-3 text-sm text-[var(--vault-text-secondary)]">
            {tc("questions")}{" "}
            <a href="mailto:support@cryptotax.defi" className="text-primary hover:underline">
              {tc("contactSupport")}
            </a>
          </p>
        </div>
      </section>
    </div>
  );
}
