"use client";

import { useLocale, useTranslations } from "next-intl";
import { TerminalHero } from "@/components/landing/TerminalHero";
import { InfiniteChainTicker } from "@/components/landing/InfiniteChainTicker";
import { BentoGrid } from "@/components/landing/BentoGrid";
import { ArchitectureSplit } from "@/components/landing/ArchitectureSplit";
import { ComparisonTable } from "@/components/landing/ComparisonTable";
import { PricingRow } from "@/components/landing/PricingRow";
import { GermanFeatures } from "@/components/landing/GermanFeatures";
import { FooterCTA } from "@/components/landing/FooterCTA";

/* ================================================================
   LANDING PAGE - Structurally distinctive layout:

   1. Terminal Hero (full-bleed, asymmetric, oversized type + live terminal)
   2. Infinite Chain Ticker (horizontal auto-scroll, not flex-wrap badges)
   3. Bento Grid (asymmetric card sizes, not 3-equal-columns)
   4. Architecture Split (left/right contrast panels, not centered emojis)
   5. Comparison Table (Bloomberg-style data table, not comparison cards)
   6. [DE only] German Features (Spekulationsfrist rings + Freigrenze cliff)
   7. Pricing Row (toggle, left-aligned header, not centered 3-col)
   8. Footer CTA (oversized left-aligned text, not centered box)
   ================================================================ */

export default function LandingPage() {
  const t = useTranslations("landing");
  const locale = useLocale();
  const isDE = locale === "de";

  return (
    <div className="flex flex-col">
      {/* 1 - Hero: terminal aesthetic, not a generic card mockup */}
      <TerminalHero t={t} />

      {/* 2 - Chain ticker: infinite horizontal scroll */}
      <InfiniteChainTicker />

      {/* 3 - Bento grid: asymmetric feature cards */}
      <BentoGrid t={t} />

      {/* 4 - Architecture: split-screen privacy diagram */}
      <ArchitectureSplit t={t} />

      {/* 5 - Comparison: dense data table */}
      <ComparisonTable t={t} />

      {/* 6 - German-specific: Spekulationsfrist + Freigrenze (DE only) */}
      {isDE && <GermanFeatures t={t} />}

      {/* 7 - Pricing */}
      <PricingRow t={t} locale={locale} />

      {/* 8 - Footer CTA */}
      <FooterCTA t={t} />
    </div>
  );
}
