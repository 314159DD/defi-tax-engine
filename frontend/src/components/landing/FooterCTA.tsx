"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Link } from "@/i18n/navigation";

/* ── Footer CTA: full-bleed, oversized text, not centered box ── */

export function FooterCTA({ t }: { t: (k: string) => string }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });

  return (
    <section
      ref={ref}
      className="relative py-32 sm:py-40 px-4 sm:px-6 lg:px-8 overflow-hidden"
    >
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.06] via-transparent to-blue-500/[0.02]" />
      <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-primary/[0.03] rounded-full blur-[150px]" />

      <div className="relative max-w-[1400px] mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
        >
          {/* Oversized text - left aligned, not centered */}
          <h2 className="font-display text-[clamp(2rem,4vw,3.5rem)] font-bold leading-[1.05] tracking-[-0.03em] max-w-3xl mb-8">
            {t("footerCtaTitle2")}
          </h2>

          <div className="flex flex-wrap items-center gap-4 sm:gap-6">
            <Link href="/estimate" className="btn-primary text-base px-8 py-3">
              {t("footerCtaButton2")}
            </Link>
            <span className="font-mono text-xs text-[var(--vault-text-tertiary)]">
              {t("footerCtaSubline")}
            </span>
          </div>
        </motion.div>

        {/* Bottom: minimal footer links */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : {}}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="mt-24 sm:mt-32 pt-8 border-t border-white/[0.04] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
        >
          <div className="flex items-center gap-0">
            <span className="font-mono text-sm font-bold text-foreground">CRYPTO</span>
            <span className="font-mono text-sm font-bold text-primary">TAX</span>
            <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)] ml-2">DeFi</span>
          </div>

          <div className="flex flex-wrap gap-6">
            {[
              { href: "/pricing", label: t("footerPricing") || "Pricing" },
              { href: "/blog", label: t("footerBlog") || "Blog" },
              { href: "/compare/koinly", label: t("footerCompare") || "Compare" },
            ].map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="font-mono text-xs text-[var(--vault-text-tertiary)] hover:text-primary transition-colors"
              >
                {link.label}
              </Link>
            ))}
          </div>

          <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)]">
            &copy; {new Date().getFullYear()} CryptoTax DeFi
          </span>
        </motion.div>
      </div>
    </section>
  );
}
