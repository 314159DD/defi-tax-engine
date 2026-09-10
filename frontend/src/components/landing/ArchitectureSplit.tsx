"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";

/* ── Split-screen architecture diagram ──
   Left side: dark, shows "Your Device" with data flowing
   Right side: darker, shows "Our Server" with crossed-out items
   Visually communicates: data stays left, never crosses to right
── */

export function ArchitectureSplit({ t }: { t: (k: string) => string }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section id="architecture" ref={ref} className="py-24 sm:py-32 px-4 sm:px-6 lg:px-8 overflow-hidden">
      <div className="max-w-[1400px] mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.5 }}
          className="mb-12 sm:mb-16 max-w-xl"
        >
          <span className="font-mono text-[10px] sm:text-xs tracking-[0.3em] uppercase text-primary/80 mb-3 block">
            {t("archLabel") || "Privacy architecture"}
          </span>
          <h2 className="font-display text-3xl sm:text-4xl font-bold leading-[1.05] tracking-tight">
            {t("archTitle") || "Your data never leaves your browser"}
          </h2>
        </motion.div>

        {/* Split panels */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-0 md:gap-0 rounded-xl overflow-hidden border border-white/[0.06]">

          {/* LEFT: Your Device - brighter */}
          <motion.div
            initial={{ opacity: 0, x: -24 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="bg-[oklch(0.16_0.01_75/30%)] p-8 sm:p-10 lg:p-12 border-b md:border-b-0 md:border-r border-white/[0.06]"
          >
            <div className="flex items-center gap-3 mb-8">
              <div className="w-3 h-3 rounded-full bg-[var(--vault-positive)]" />
              <span className="font-mono text-sm font-bold text-foreground uppercase tracking-wider">
                {t("archDeviceTitle") || "Your Device"}
              </span>
            </div>

            <div className="space-y-4">
              {[
                { label: "Wallet addresses", mono: "0x7a25...f3e2" },
                { label: "Transaction history", mono: "847 txs" },
                { label: "Cost basis / tax lots", mono: "$142,891.32" },
                { label: "Gains & losses", mono: "+$18,035.96" },
                { label: "Tax reports (PDF)", mono: "form8949.pdf" },
                { label: "IndexedDB storage", mono: "encrypted" },
              ].map((item, i) => (
                <motion.div
                  key={item.label}
                  initial={{ opacity: 0, x: -12 }}
                  animate={inView ? { opacity: 1, x: 0 } : {}}
                  transition={{ duration: 0.4, delay: 0.3 + i * 0.08 }}
                  className="flex items-center justify-between py-2.5 border-b border-white/[0.04] last:border-0"
                >
                  <span className="text-sm text-[var(--vault-text-secondary)]">{item.label}</span>
                  <span className="font-mono text-xs text-primary/80">{item.mono}</span>
                </motion.div>
              ))}
            </div>

            <div className="mt-8 px-4 py-3 rounded-lg bg-[var(--vault-positive)]/5 border border-[var(--vault-positive)]/10">
              <span className="font-mono text-[11px] text-[var(--vault-positive)] leading-relaxed">
                {t("archDeviceNote") || "All computation runs in a Web Worker on your machine. Financial data is encrypted in IndexedDB."}
              </span>
            </div>
          </motion.div>

          {/* RIGHT: Our Server - dimmer */}
          <motion.div
            initial={{ opacity: 0, x: 24 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="bg-[oklch(0.11_0.005_260/80%)] p-8 sm:p-10 lg:p-12"
          >
            <div className="flex items-center gap-3 mb-8">
              <div className="w-3 h-3 rounded-full bg-[var(--vault-text-tertiary)]" />
              <span className="font-mono text-sm font-bold text-[var(--vault-text-tertiary)] uppercase tracking-wider">
                {t("archServerTitle") || "Our Server"}
              </span>
            </div>

            <div className="space-y-4">
              {[
                { label: "Wallet addresses", status: "never stored" },
                { label: "Transaction data", status: "never stored" },
                { label: "Financial figures", status: "never stored" },
                { label: "Tax calculations", status: "never stored" },
              ].map((item, i) => (
                <motion.div
                  key={item.label}
                  initial={{ opacity: 0, x: 12 }}
                  animate={inView ? { opacity: 1, x: 0 } : {}}
                  transition={{ duration: 0.4, delay: 0.4 + i * 0.08 }}
                  className="flex items-center justify-between py-2.5 border-b border-white/[0.03] last:border-0"
                >
                  <span className="text-sm text-[var(--vault-text-tertiary)] line-through decoration-[var(--vault-negative)]/40">{item.label}</span>
                  <span className="font-mono text-[10px] text-[var(--vault-negative)]/60 uppercase tracking-wider">{item.status}</span>
                </motion.div>
              ))}
            </div>

            {/* Divider */}
            <div className="h-px bg-white/[0.06] my-6" />

            {/* What WE do handle */}
            <div className="mb-4">
              <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)] uppercase tracking-wider">
                {t("archServerHandles") || "We only handle:"}
              </span>
            </div>
            <div className="space-y-3">
              {[
                { label: "Chain API proxy", desc: "We pay for 13+ API keys" },
                { label: "Authentication", desc: "Supabase JWT" },
                { label: "Billing", desc: "Stripe subscription" },
              ].map((item, i) => (
                <motion.div
                  key={item.label}
                  initial={{ opacity: 0, x: 12 }}
                  animate={inView ? { opacity: 1, x: 0 } : {}}
                  transition={{ duration: 0.4, delay: 0.6 + i * 0.08 }}
                  className="flex items-center justify-between"
                >
                  <span className="text-sm text-[var(--vault-text-secondary)]">{item.label}</span>
                  <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)]">{item.desc}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
