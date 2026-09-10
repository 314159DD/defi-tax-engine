"use client";

import { motion, useInView } from "framer-motion";
import { useRef, useState } from "react";
import { Link } from "@/i18n/navigation";

/* ── Pricing: horizontal row, not 3 equal cards ──
   Toggle between monthly/annual. Single highlighted plan.
   Compact, data-dense layout.
── */

export function PricingRow({ t, locale }: { t: (k: string) => string; locale: string }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const [annual, setAnnual] = useState(false);

  const isDE = locale === "de";

  const plans = isDE
    ? [
        {
          name: t("dePricingFreeTitle") || "Kostenlos",
          price: "0 EUR",
          period: "",
          features: [t("dePricingFreeDesc") || "1 Wallet, nur Ethereum"],
          cta: t("dePricingCta") || "Starten",
          highlight: false,
        },
        {
          name: t("dePricingStandardTitle") || "Standard",
          price: annual ? "79 EUR" : "99 EUR",
          period: `/${t("dePricingPeriod") || "Steuerjahr"}`,
          features: [t("dePricingStandardDesc") || "5 Wallets, alle Chains, alle Reports"],
          cta: t("dePricingCta") || "Starten",
          highlight: true,
          badge: t("dePricingPopular") || "Beliebt",
        },
        {
          name: t("dePricingPremiumTitle") || "Premium",
          price: annual ? "149 EUR" : "179 EUR",
          period: `/${t("dePricingPeriod") || "Steuerjahr"}`,
          features: [t("dePricingPremiumDesc") || "Unbegrenzte Wallets + DeFi + CPA Portal"],
          cta: t("dePricingCta") || "Starten",
          highlight: false,
        },
      ]
    : [
        {
          name: t("pricingFreeTitle") || "Free",
          price: "$0",
          period: "",
          features: [t("pricingFreeF1") || "1 wallet, Ethereum only"],
          cta: t("pricingStartFree") || "Start free",
          highlight: false,
        },
        {
          name: t("pricingProTitle") || "Pro",
          price: annual ? "$79" : "$99",
          period: "/yr",
          features: [t("pricingProF1") || "5 wallets, all chains, all reports"],
          cta: t("pricingStartFree") || "Start free",
          highlight: true,
          badge: t("pricingPopular") || "Most popular",
        },
        {
          name: t("pricingUnlimitedTitle") || "Unlimited",
          price: annual ? "$179" : "$199",
          period: "/yr",
          features: [t("pricingUnlimitedF1") || "Unlimited wallets + CPA portal"],
          cta: t("pricingStartFree") || "Start free",
          highlight: false,
        },
      ];

  return (
    <section ref={ref} className="py-24 sm:py-32 px-4 sm:px-6 lg:px-8">
      <div className="max-w-[1400px] mx-auto">
        {/* Header + toggle */}
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-6 mb-12 sm:mb-16">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.5 }}
          >
            <span className="font-mono text-[10px] sm:text-xs tracking-[0.3em] uppercase text-primary/80 mb-3 block">
              {t("pricingLabel") || "Pricing"}
            </span>
            <h2 className="font-display text-3xl sm:text-4xl font-bold leading-[1.05] tracking-tight">
              {isDE ? t("dePricingTitle2") : t("pricingTitle2")}
            </h2>
          </motion.div>

          {/* Annual toggle */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="flex items-center gap-3"
          >
            <span className={`font-mono text-xs ${!annual ? "text-foreground" : "text-[var(--vault-text-tertiary)]"}`}>
              {isDE ? "Monatlich" : "Monthly"}
            </span>
            <button
              onClick={() => setAnnual(!annual)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                annual ? "bg-primary" : "bg-white/10"
              }`}
            >
              <div
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  annual ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
            <span className={`font-mono text-xs ${annual ? "text-foreground" : "text-[var(--vault-text-tertiary)]"}`}>
              {isDE ? "Jhrlich" : "Annual"}
              {annual && (
                <span className="text-[var(--vault-positive)] ml-1">
                  {isDE ? "(-20%)" : "(-20%)"}
                </span>
              )}
            </span>
          </motion.div>
        </div>

        {/* Plans row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-5">
          {plans.map((plan, i) => (
            <motion.div
              key={plan.name}
              initial={{ opacity: 0, y: 20 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.1 + i * 0.1 }}
              className={`
                relative rounded-xl p-6 sm:p-8 backdrop-blur-xl
                ${plan.highlight
                  ? "bg-[oklch(0.15_0.01_75/50%)] border-2 border-primary/30 shadow-[0_0_60px_oklch(0.82_0.17_75/0.06)]"
                  : "bg-[oklch(0.15_0.005_260/60%)] border border-white/[0.06]"
                }
              `}
            >
              {plan.badge && (
                <span className="absolute -top-3 left-6 bg-primary text-primary-foreground font-mono text-[10px] px-3 py-1 rounded-full font-bold">
                  {plan.badge}
                </span>
              )}

              <div className="flex items-baseline gap-2 mb-1">
                <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)] uppercase tracking-wider">
                  {plan.name}
                </span>
              </div>

              <div className="flex items-baseline gap-1 mb-4">
                <span className={`font-display text-3xl sm:text-4xl font-bold ${plan.highlight ? "text-gradient-amber" : "text-foreground"}`}>
                  {plan.price}
                </span>
                {plan.period && (
                  <span className="font-mono text-xs text-[var(--vault-text-tertiary)]">
                    {plan.period}
                  </span>
                )}
              </div>

              <p className="text-sm text-[var(--vault-text-secondary)] mb-6 leading-relaxed">
                {plan.features[0]}
              </p>

              <Link
                href="/estimate"
                className={`block text-center font-mono text-sm font-medium py-2.5 rounded-lg transition-all ${
                  plan.highlight
                    ? "bg-primary text-primary-foreground hover:brightness-110"
                    : "border border-white/10 text-foreground hover:border-primary/40"
                }`}
              >
                {plan.cta}
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
