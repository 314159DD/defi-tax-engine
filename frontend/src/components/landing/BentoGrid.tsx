"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";

/* ── Bento Grid: Asymmetric feature showcase ── */
/* Layout: 2 tall left + 2 short stacked right on desktop */

function BentoCard({
  children,
  className = "",
  delay = 0,
  accent = false,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  accent?: boolean;
}) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 24 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.5, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={`
        relative overflow-hidden rounded-xl p-6 sm:p-8
        ${accent
          ? "bg-[oklch(0.15_0.01_75/50%)] border border-primary/20 shadow-[0_0_60px_oklch(0.82_0.17_75/0.04)]"
          : "bg-[oklch(0.15_0.005_260/60%)] border border-white/[0.06]"
        }
        backdrop-blur-xl
        ${className}
      `}
    >
      {children}
    </motion.div>
  );
}

export function BentoGrid({ t }: { t: (k: string) => string }) {
  return (
    <section className="py-24 sm:py-32 px-4 sm:px-6 lg:px-8">
      <div className="max-w-[1400px] mx-auto">
        {/* Section header - left-aligned */}
        <div className="mb-12 sm:mb-16 max-w-xl">
          <span className="font-mono text-[10px] sm:text-xs tracking-[0.3em] uppercase text-primary/80 mb-3 block">
            {t("bentoLabel") || "Why us"}
          </span>
          <h2 className="font-display text-3xl sm:text-4xl font-bold leading-[1.05] tracking-tight">
            {t("problemTitle2")}
          </h2>
        </div>

        {/* Bento layout */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 sm:gap-5">

          {/* Card 1: DeFi categorization - spans 2 cols on lg, tall */}
          <BentoCard className="md:col-span-2 md:row-span-2" accent delay={0}>
            <div className="flex flex-col h-full">
              <div className="flex items-start justify-between mb-6">
                <div>
                  <span className="font-mono text-[10px] text-primary/60 uppercase tracking-wider block mb-1">
                    {t("problemLpLabel")}
                  </span>
                  <h3 className="font-display text-xl sm:text-2xl font-bold">
                    {t("bentoDefiTitle") || "DeFi-Native Categorization"}
                  </h3>
                </div>
              </div>

              <p className="text-[var(--vault-text-secondary)] text-sm leading-relaxed mb-8 max-w-lg">
                {t("bentoDefiDesc") || "23 DeFi protocols. Uniswap V3 concentrated liquidity, cross-chain bridges, auto-compounding vaults, liquid staking - all categorized automatically."}
              </p>

              {/* Visual: categorization rules as data rows */}
              <div className="mt-auto space-y-2">
                {[
                  { tag: "SWAP", proto: "Uniswap V3", hash: "0xa3f1...c8e2", color: "text-blue-400" },
                  { tag: "BRIDGE", proto: "Across Protocol", hash: "0xb7e2...d1f4", color: "text-purple-400" },
                  { tag: "LP_ADD", proto: "Curve 3pool", hash: "0xc9d3...a4b7", color: "text-cyan-400" },
                  { tag: "VAULT", proto: "Yearn yvUSDC", hash: "0xd1f4...b7c9", color: "text-emerald-400" },
                  { tag: "STAKE", proto: "Lido stETH", hash: "0xe5a8...c3d1", color: "text-amber-300" },
                ].map((row) => (
                  <div key={row.tag} className="flex items-center gap-3 font-mono text-[11px] py-1.5 px-3 rounded-md bg-white/[0.02] border border-white/[0.03]">
                    <span className={`${row.color} font-bold w-16 shrink-0`}>{row.tag}</span>
                    <span className="text-[var(--vault-text-tertiary)] w-14 shrink-0 hidden sm:block">{row.hash}</span>
                    <span className="text-[var(--vault-text-secondary)] ml-auto">{row.proto}</span>
                  </div>
                ))}
              </div>
            </div>
          </BentoCard>

          {/* Card 2: Privacy - single col */}
          <BentoCard delay={0.1}>
            <span className="font-mono text-[10px] text-primary/60 uppercase tracking-wider block mb-1">
              {t("bentoPrivacyLabel") || "Architecture"}
            </span>
            <h3 className="font-display text-lg sm:text-xl font-bold mb-3">
              {t("privacyHeadline")}
            </h3>
            <p className="text-[var(--vault-text-secondary)] text-sm leading-relaxed mb-6">
              {t("privacySubline")}
            </p>

            {/* Data flow diagram - vertical, compact */}
            <div className="space-y-3">
              {[
                { icon: "01", label: t("privacyFlowDevice") || "Your browser", accent: true },
                { icon: "02", label: t("privacyFlowCalc") || "Web Worker", accent: true },
                { icon: "03", label: t("privacyFlowPdf") || "PDF export", accent: true },
              ].map((step, i) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="font-mono text-[10px] text-primary/80 w-5">{step.icon}</span>
                  <div className="h-px flex-1 bg-gradient-to-r from-primary/20 to-transparent" />
                  <span className="font-mono text-xs text-[var(--vault-text-secondary)]">{step.label}</span>
                </div>
              ))}
            </div>

            <div className="mt-6 px-3 py-2 rounded-md bg-[var(--vault-positive)]/5 border border-[var(--vault-positive)]/10">
              <span className="font-mono text-[10px] text-[var(--vault-positive)]">
                {t("bentoPrivacyBadge") || "Zero financial data on our servers. Ever."}
              </span>
            </div>
          </BentoCard>

          {/* Card 3: Multi-method - single col */}
          <BentoCard delay={0.2}>
            <span className="font-mono text-[10px] text-primary/60 uppercase tracking-wider block mb-1">
              {t("bentoMethodLabel") || "Tax methods"}
            </span>
            <h3 className="font-display text-lg sm:text-xl font-bold mb-3">
              {t("bentoMethodTitle") || "FIFO / LIFO / HIFO"}
            </h3>
            <p className="text-[var(--vault-text-secondary)] text-sm leading-relaxed mb-6">
              {t("bentoMethodDesc") || "Compare all three methods side-by-side. Pick the one that saves you the most."}
            </p>

            {/* Method comparison mini-table */}
            <div className="space-y-2">
              {[
                { method: "FIFO", tax: "$4,231", delta: "baseline", highlight: false },
                { method: "LIFO", tax: "$3,847", delta: "-$384", highlight: false },
                { method: "HIFO", tax: "$2,912", delta: "-$1,319", highlight: true },
              ].map((row) => (
                <div
                  key={row.method}
                  className={`flex items-center justify-between font-mono text-xs py-2 px-3 rounded-md ${
                    row.highlight
                      ? "bg-primary/10 border border-primary/20"
                      : "bg-white/[0.02] border border-white/[0.03]"
                  }`}
                >
                  <span className={`font-bold ${row.highlight ? "text-primary" : "text-foreground"}`}>{row.method}</span>
                  <span className="text-[var(--vault-text-secondary)]">{row.tax}</span>
                  <span className={row.highlight ? "text-[var(--vault-positive)]" : "text-[var(--vault-text-tertiary)]"}>
                    {row.delta}
                  </span>
                </div>
              ))}
            </div>
          </BentoCard>

          {/* Card 4: Reports - full width bottom */}
          <BentoCard className="md:col-span-3" delay={0.3}>
            <div className="flex flex-col sm:flex-row sm:items-center gap-6 sm:gap-12">
              <div className="shrink-0 max-w-sm">
                <span className="font-mono text-[10px] text-primary/60 uppercase tracking-wider block mb-1">
                  {t("bentoReportsLabel") || "Export"}
                </span>
                <h3 className="font-display text-lg sm:text-xl font-bold mb-2">
                  {t("bentoReportsTitle") || "Every format your CPA needs"}
                </h3>
                <p className="text-[var(--vault-text-secondary)] text-sm leading-relaxed">
                  {t("bentoReportsDesc") || "Form 8949, Schedule D, TurboTax CSV, 1099-DA reconciliation. For Germany: Anlage SO, WISO Steuer, DATEV."}
                </p>
              </div>

              {/* Report format badges - horizontal scroll on mobile */}
              <div className="flex flex-wrap gap-2 sm:gap-2.5">
                {[
                  "Form 8949", "Schedule D", "TurboTax", "1099-DA",
                  "Anlage SO", "WISO", "DATEV", "CSV",
                ].map((fmt) => (
                  <span
                    key={fmt}
                    className="px-3 py-1.5 rounded-md font-mono text-[11px] bg-white/[0.03] border border-white/[0.06] text-[var(--vault-text-secondary)] hover:border-primary/20 hover:text-primary transition-colors"
                  >
                    {fmt}
                  </span>
                ))}
              </div>
            </div>
          </BentoCard>
        </div>
      </div>
    </section>
  );
}
