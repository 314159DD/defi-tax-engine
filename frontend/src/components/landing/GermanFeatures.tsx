"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";

/* ── German-specific features: Spekulationsfrist + Freigrenze ──
   Shown only on DE locale. Uses data visualization as design element.
── */

function CountdownRing({ days, total, token, exempt }: { days: number; total: number; token: string; exempt: boolean }) {
  const pct = ((total - days) / total) * 100;
  const circumference = 2 * Math.PI * 38;
  const dashoffset = circumference - (pct / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative w-24 h-24">
        <svg viewBox="0 0 80 80" className="w-full h-full -rotate-90">
          {/* Track */}
          <circle cx="40" cy="40" r="38" fill="none" stroke="oklch(1 0 0 / 4%)" strokeWidth="3" />
          {/* Progress */}
          <circle
            cx="40" cy="40" r="38" fill="none"
            stroke={exempt ? "oklch(0.72 0.19 155)" : "oklch(0.82 0.17 75)"}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashoffset}
            className="transition-all duration-1000"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-lg font-bold text-foreground">
            {exempt ? "0" : days}
          </span>
          <span className="font-mono text-[9px] text-[var(--vault-text-tertiary)]">
            {exempt ? "STEUERFREI" : "TAGE"}
          </span>
        </div>
      </div>
      <span className="font-mono text-xs text-[var(--vault-text-secondary)]">{token}</span>
    </div>
  );
}

export function GermanFeatures({ t }: { t: (k: string) => string }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });

  return (
    <section ref={ref} className="py-24 sm:py-32 px-4 sm:px-6 lg:px-8">
      <div className="max-w-[1400px] mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
          className="mb-12 sm:mb-16 max-w-xl"
        >
          <span className="font-mono text-[10px] sm:text-xs tracking-[0.3em] uppercase text-primary/80 mb-3 block">
            DACH-spezifisch
          </span>
          <h2 className="font-display text-3xl sm:text-4xl font-bold leading-[1.05] tracking-tight">
            {t("deFeatureTitle") || "Spekulationsfrist. Freigrenze. Korrekt gerechnet."}
          </h2>
          {t("deFeatureSubtitle") && (
            <p className="mt-3 text-sm text-muted-foreground font-mono">
              {t("deFeatureSubtitle")}
            </p>
          )}
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Spekulationsfrist card */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="rounded-xl bg-[oklch(0.15_0.005_260/60%)] border border-white/[0.06] backdrop-blur-xl p-8"
          >
            <span className="font-mono text-[10px] text-primary/60 uppercase tracking-wider block mb-1">
              &sect; 23 EStG
            </span>
            <h3 className="font-display text-xl sm:text-2xl font-bold mb-2">
              {t("deSpekTitle") || "Spekulationsfrist"}
            </h3>
            <p className="text-[var(--vault-text-secondary)] text-sm mb-8 max-w-md">
              {t("deSpekSubtitle") || "Halte-Countdown pro Position. Tag 365 = steuerpflichtig, Tag 366 = steuerfrei."}
            </p>

            {/* Visual: countdown rings */}
            <div className="flex justify-center gap-8 sm:gap-12">
              <CountdownRing days={47} total={365} token="2.4 ETH" exempt={false} />
              <CountdownRing days={182} total={365} token="500 USDC" exempt={false} />
              <CountdownRing days={0} total={365} token="1.8 UNI" exempt={true} />
            </div>
          </motion.div>

          {/* Freigrenze card */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="rounded-xl bg-[oklch(0.15_0.005_260/60%)] border border-white/[0.06] backdrop-blur-xl p-8"
          >
            <span className="font-mono text-[10px] text-primary/60 uppercase tracking-wider block mb-1">
              &sect; 23 Abs. 3 Satz 5 EStG
            </span>
            <h3 className="font-display text-xl sm:text-2xl font-bold mb-2">
              {t("deFreigrenzeTitle") || "Freigrenze"}
            </h3>
            <p className="text-[var(--vault-text-secondary)] text-sm mb-8 max-w-md">
              {t("deFreigrenzeSubtitle") || "Kein Freibetrag. Eine CLIFF-Grenze: 999,99 EUR = steuerfrei. 1.000,00 EUR = ALLES steuerpflichtig."}
            </p>

            {/* Cliff visualization */}
            <div className="relative">
              {/* Bar */}
              <div className="h-12 rounded-lg bg-[var(--vault-bg-elevated)] relative overflow-hidden">
                {/* Filled portion */}
                <div
                  className="absolute inset-y-0 left-0 rounded-l-lg bg-gradient-to-r from-[var(--vault-positive)] to-[var(--vault-warning)]"
                  style={{ width: "68%" }}
                />
                {/* Cliff line */}
                <div className="absolute right-0 top-0 bottom-0 w-0.5 bg-[var(--vault-negative)]" />
                {/* Current value overlay */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="font-mono text-sm font-bold text-white drop-shadow-lg">
                    680 EUR
                  </span>
                </div>
              </div>

              {/* Labels */}
              <div className="flex justify-between mt-2">
                <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)]">0 EUR</span>
                <div className="flex flex-col items-end">
                  <span className="font-mono text-[10px] text-[var(--vault-negative)] font-bold">CLIFF: 1.000 EUR</span>
                  <span className="font-mono text-[9px] text-[var(--vault-text-tertiary)]">
                    {t("deFreigrenzeWarn") || "1 EUR drber = alles steuerpflichtig"}
                  </span>
                </div>
              </div>

              {/* Status badge */}
              <div className="mt-4 px-3 py-2 rounded-md bg-[var(--vault-positive)]/5 border border-[var(--vault-positive)]/10 inline-block">
                <span className="font-mono text-[10px] text-[var(--vault-positive)]">
                  320 EUR Puffer verbleibend
                </span>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
