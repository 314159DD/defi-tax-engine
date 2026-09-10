"use client";

import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import { Link } from "@/i18n/navigation";

/* ── Simulated terminal output - shows real tx categorization ── */
const TERMINAL_LINES = [
  { text: "$ cryptotax import 0x7a25...f3e2 --chain ethereum", type: "cmd" as const, delay: 0 },
  { text: "  fetching 847 transactions...", type: "dim" as const, delay: 400 },
  { text: "  [SWAP]     0xa3f1..c8 │ 2.4 ETH → 4,231 USDC   │ Uniswap V3", type: "swap" as const, delay: 900 },
  { text: "  [BRIDGE]   0xb7e2..d1 │ 1,000 USDC → Arbitrum   │ Across Protocol", type: "bridge" as const, delay: 1300 },
  { text: "  [LP_ADD]   0xc9d3..a4 │ 500 USDC + 0.3 ETH      │ Uniswap V3 #48291", type: "lp" as const, delay: 1700 },
  { text: "  [STAKE]    0xd1f4..b7 │ 32 ETH → stETH           │ Lido", type: "stake" as const, delay: 2100 },
  { text: "  [AIRDROP]  0xe5a8..c3 │ 1,247 ARB                │ Arbitrum Foundation", type: "airdrop" as const, delay: 2500 },
  { text: "  847 txs categorized │ 0 errors │ 23 DeFi protocols detected", type: "success" as const, delay: 3000 },
  { text: "", type: "dim" as const, delay: 3200 },
  { text: "$ cryptotax calculate --method FIFO --year 2025", type: "cmd" as const, delay: 3400 },
  { text: "  Short-term gains:  $12,847.32", type: "gain" as const, delay: 3900 },
  { text: "  Long-term gains:    $8,291.08", type: "gain" as const, delay: 4200 },
  { text: "  Losses harvested:  -$3,102.44", type: "loss" as const, delay: 4500 },
  { text: "  Net taxable:        $18,035.96", type: "result" as const, delay: 4900 },
  { text: "  Form 8949 ready │ Schedule D ready │ TurboTax CSV ready", type: "success" as const, delay: 5400 },
];

const LINE_COLORS: Record<string, string> = {
  cmd: "text-primary",
  dim: "text-[var(--vault-text-tertiary)]",
  swap: "text-blue-400",
  bridge: "text-purple-400",
  lp: "text-cyan-400",
  stake: "text-emerald-400",
  airdrop: "text-amber-300",
  success: "text-[var(--vault-positive)]",
  gain: "text-[var(--vault-positive)]",
  loss: "text-[var(--vault-negative)]",
  result: "text-primary font-bold",
};

function TerminalWindow() {
  const [visibleLines, setVisibleLines] = useState<number>(0);
  const termRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timers: NodeJS.Timeout[] = [];
    TERMINAL_LINES.forEach((line, i) => {
      timers.push(
        setTimeout(() => {
          setVisibleLines(i + 1);
          if (termRef.current) {
            termRef.current.scrollTop = termRef.current.scrollHeight;
          }
        }, line.delay)
      );
    });
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="relative w-full">
      {/* Terminal chrome */}
      <div className="rounded-t-lg bg-[oklch(0.11_0.005_260)] border border-b-0 border-white/[0.06] px-4 py-2.5 flex items-center gap-2">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[var(--vault-negative)]/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-[var(--vault-warning)]/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-[var(--vault-positive)]/60" />
        </div>
        <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)] ml-2">
          cryptotax - ~/portfolio
        </span>
      </div>

      {/* Terminal body */}
      <div
        ref={termRef}
        className="rounded-b-lg bg-[oklch(0.09_0.005_260)] border border-t-0 border-white/[0.06] p-4 font-mono text-[11px] sm:text-xs leading-relaxed h-[320px] sm:h-[380px] overflow-hidden"
      >
        {TERMINAL_LINES.slice(0, visibleLines).map((line, i) => (
          <div
            key={i}
            className={`${LINE_COLORS[line.type]} whitespace-pre opacity-0 animate-[fadeIn_0.15s_ease_forwards]`}
          >
            {line.text || "\u00A0"}
          </div>
        ))}
        {/* Blinking cursor */}
        <span className="inline-block w-[7px] h-[14px] bg-primary/80 animate-pulse ml-0.5" />
      </div>

      {/* Ambient glow behind terminal */}
      <div className="absolute -inset-4 bg-primary/[0.03] rounded-2xl blur-2xl -z-10" />
    </div>
  );
}

/* ── Main Hero Component ── */
export function TerminalHero({ t }: { t: (k: string) => string }) {
  return (
    <section className="relative min-h-screen overflow-hidden">
      {/* Background: subtle dot grid fading out */}
      <div className="absolute inset-0 grid-pattern opacity-40" />

      {/* Gradient orbs */}
      <div className="absolute -top-40 -right-40 w-[600px] h-[600px] bg-primary/[0.04] rounded-full blur-[150px]" />
      <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-blue-500/[0.02] rounded-full blur-[120px]" />

      <div className="relative max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 pt-16 sm:pt-24 pb-8">
        {/* Top: oversized typography - left-aligned, not centered */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-8 sm:mb-12"
        >
          <div className="font-mono text-[10px] sm:text-xs tracking-[0.3em] uppercase text-primary/80 mb-4 sm:mb-6">
            {t("heroLabel")}
          </div>

          {/* Headline: massive type with tight leading */}
          <h1 className="font-display text-4xl md:text-5xl xl:text-6xl font-bold leading-[0.95] tracking-[-0.04em]">
            <span className="block text-foreground">{t("heroLine1")}</span>
            <span className="block text-foreground">{t("heroLine2")}</span>
          </h1>
        </motion.div>

        {/* Two-column: subtitle+CTA left, terminal right */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 md:gap-12 items-start">
          {/* Left col: 5/12 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="md:col-span-5 flex flex-col gap-8"
          >
            <p className="text-[var(--vault-text-secondary)] text-base sm:text-lg leading-relaxed max-w-md">
              {t("heroSubtitle2")}
            </p>

            {t("heroTrustLine") && (
              <p className="font-mono text-sm text-primary font-medium">
                {t("heroTrustLine")}
              </p>
            )}

            <div className="flex flex-wrap gap-3">
              <Link href="/estimate" className="btn-primary">
                {t("heroCta1")}
              </Link>
              <a href="#architecture" className="btn-ghost">
                {t("heroCta2")}
              </a>
            </div>

            {/* Proof points - horizontal, not dots */}
            <div className="flex flex-wrap gap-x-6 gap-y-2 pt-4 border-t border-white/[0.06]">
              {[t("trustTests"), t("trustChains"), t("trustLocal")].map((item, i) => (
                <span key={i} className="font-mono text-[10px] sm:text-[11px] text-[var(--vault-text-tertiary)] uppercase tracking-wider">
                  {item}
                </span>
              ))}
            </div>
          </motion.div>

          {/* Right col: 7/12 - terminal */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.4 }}
            className="md:col-span-7"
          >
            <TerminalWindow />
          </motion.div>
        </div>
      </div>
    </section>
  );
}
