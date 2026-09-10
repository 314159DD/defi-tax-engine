"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";

/* ── Dense comparison table - not 3 equal cards ──
   Single table showing us vs competitors on specific DeFi scenarios.
   Bloomberg-style data table aesthetic.
── */

type Row = {
  scenario: string;
  competitors: string;
  us: string;
  competitorFails: boolean;
};

export function ComparisonTable({ t }: { t: (k: string) => string }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });

  const rows: Row[] = [
    {
      scenario: t("compRowLp") || "Uniswap V3 concentrated LP",
      competitors: t("compRowLpTheirs") || "Categorized as 'Unknown'",
      us: t("compRowLpOurs") || "Full LP_ADD/LP_REMOVE with IL tracking",
      competitorFails: true,
    },
    {
      scenario: t("compRowBridge") || "Cross-chain bridge (Across)",
      competitors: t("compRowBridgeTheirs") || "Counted as taxable disposal",
      us: t("compRowBridgeOurs") || "Recognized as non-taxable transfer",
      competitorFails: true,
    },
    {
      scenario: t("compRowStaking") || "Liquid staking (stETH, rETH)",
      competitors: t("compRowStakingTheirs") || "Treated as swap → capital gains",
      us: t("compRowStakingOurs") || "Equivalent token mapping → no event",
      competitorFails: true,
    },
    {
      scenario: t("compRowVault") || "Auto-compounding vault",
      competitors: t("compRowVaultTheirs") || "Ignored entirely",
      us: t("compRowVaultOurs") || "Tracks deposit/withdraw + yield accrual",
      competitorFails: true,
    },
    {
      scenario: t("compRowSpam") || "Spam token airdrops",
      competitors: t("compRowSpamTheirs") || "Counted as income",
      us: t("compRowSpamOurs") || "Smart filter removes 99%+ spam",
      competitorFails: true,
    },
    {
      scenario: t("compRowPrivacy") || "Financial data storage",
      competitors: t("compRowPrivacyTheirs") || "Stored on their servers",
      us: t("compRowPrivacyOurs") || "Never leaves your browser",
      competitorFails: true,
    },
  ];

  return (
    <section ref={ref} className="py-24 sm:py-32 px-4 sm:px-6 lg:px-8 bg-[oklch(0.11_0.005_260)]">
      <div className="max-w-[1400px] mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
          className="mb-12 sm:mb-16 max-w-xl"
        >
          <span className="font-mono text-[10px] sm:text-xs tracking-[0.3em] uppercase text-primary/80 mb-3 block">
            {t("compLabel") || "Head-to-head"}
          </span>
          <h2 className="font-display text-3xl sm:text-4xl font-bold leading-[1.05] tracking-tight">
            {t("compTitle") || "Where others fail, we categorize"}
          </h2>
        </motion.div>

        {/* Table - horizontal scroll on mobile */}
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
          <div className="min-w-[640px]">
            {/* Header row */}
            <div className="grid grid-cols-[1.2fr_1fr_1fr] gap-px mb-px">
              <div className="px-4 py-3 bg-white/[0.02] rounded-tl-lg">
                <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)] uppercase tracking-wider">
                  {t("compColScenario") || "DeFi Scenario"}
                </span>
              </div>
              <div className="px-4 py-3 bg-white/[0.02]">
                <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)] uppercase tracking-wider">
                  {t("compColOthers") || "Koinly / CoinTracker / etc."}
                </span>
              </div>
              <div className="px-4 py-3 bg-primary/5 rounded-tr-lg">
                <span className="font-mono text-[10px] text-primary uppercase tracking-wider font-bold">
                  CryptoTax DeFi
                </span>
              </div>
            </div>

            {/* Data rows */}
            {rows.map((row, i) => (
              <motion.div
                key={row.scenario}
                initial={{ opacity: 0, y: 8 }}
                animate={inView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.3, delay: 0.15 + i * 0.06 }}
                className="grid grid-cols-[1.2fr_1fr_1fr] gap-px mb-px"
              >
                <div className="px-4 py-3.5 bg-white/[0.015] flex items-center">
                  <span className="text-sm text-foreground font-medium">{row.scenario}</span>
                </div>
                <div className="px-4 py-3.5 bg-white/[0.015] flex items-center gap-2">
                  <span className="w-4 h-4 rounded-full bg-[var(--vault-negative)]/10 text-[var(--vault-negative)] flex items-center justify-center text-[10px] font-bold shrink-0">
                    &#10005;
                  </span>
                  <span className="font-mono text-xs text-[var(--vault-text-secondary)]">{row.competitors}</span>
                </div>
                <div className="px-4 py-3.5 bg-primary/[0.03] flex items-center gap-2">
                  <span className="w-4 h-4 rounded-full bg-[var(--vault-positive)]/10 text-[var(--vault-positive)] flex items-center justify-center text-[10px] font-bold shrink-0">
                    &#10003;
                  </span>
                  <span className="font-mono text-xs text-[var(--vault-text-secondary)]">{row.us}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
