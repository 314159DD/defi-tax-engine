"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import { FreigrenzeBar } from "@/components/FreigrenzeBar";
import type { FreigrenzeResponse } from "@/lib/api";
import { db } from "@/db/index";
import { formatCurrency } from "@/lib/format";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2];

const MOCK_DATA: FreigrenzeResponse = {
  realized_gains_ytd: "743.50",
  freigrenze_limit: "1000.00",
  remaining_headroom: "256.50",
  status: "warning",
  projected_tax_if_exceeded: "450.00",
  year: CURRENT_YEAR,
};

export default function FreigrenzePage() {
  const t = useTranslations("freigrenze");
  const tc = useTranslations("common");
  const locale = useLocale();

  const [year, setYear] = useState(CURRENT_YEAR);
  const [data, setData] = useState<FreigrenzeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    db.disposals
      .where('[method+year+country]')
      .equals(['FIFO', year, 'DE'])
      .toArray()
      .then((disposals) => {
        if (disposals.length === 0) {
          setData({ ...MOCK_DATA, year });
        } else {
          const shortTermGains = disposals
            .filter(d => d.holdingPeriod === 'short-term' && parseFloat(d.gainLossUsd) > 0)
            .reduce((sum, d) => sum + parseFloat(d.gainLossUsd), 0);
          const limit = 1000;
          const remaining = Math.max(0, limit - shortTermGains);
          setData({
            realized_gains_ytd: String(shortTermGains),
            freigrenze_limit: String(limit),
            remaining_headroom: String(remaining),
            status: shortTermGains >= limit ? 'exceeded' : shortTermGains >= limit * 0.8 ? 'warning' : 'safe',
            projected_tax_if_exceeded: shortTermGains >= limit ? String(Math.round(shortTermGains * 0.25)) : '0',
            year,
          });
        }
        setError(null);
      })
      .catch(() => {
        setData({ ...MOCK_DATA, year });
        setError(null);
      })
      .finally(() => setLoading(false));
  }, [year]);

  const gains = data ? parseFloat(data.realized_gains_ytd) : 0;
  const limit = data ? parseFloat(data.freigrenze_limit) : 1000;
  const remaining = data ? parseFloat(data.remaining_headroom) : 0;
  const exceeded = gains > limit;
  const projectedTax = data ? parseFloat(data.projected_tax_if_exceeded) : 0;
  const pct = limit > 0 ? (gains / limit) * 100 : 0;
  const taxRate = 0.45;

  return (
    <div className="bg-[var(--vault-bg-deep)] min-h-screen">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

        {/* ── Header ────────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-12 animate-fade-in-up">
          <div>
            <h1 className="font-display text-3xl md:text-4xl font-bold text-gradient-amber">
              {t("title")}
            </h1>
            <p className="text-[var(--vault-text-secondary)] text-sm mt-2 font-sans">
              {t("subtitle")}
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Year selector - glass styled */}
            <div className="relative">
              <select
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                className={cn(
                  "glass rounded-md px-4 py-2 pr-8 font-mono text-sm font-medium",
                  "bg-transparent text-foreground appearance-none cursor-pointer",
                  "focus:outline-none focus:ring-2 focus:ring-primary/50",
                )}
              >
                {YEARS.map((y) => (
                  <option key={y} value={y} className="bg-[var(--vault-bg-surface)] text-foreground">
                    {y}
                  </option>
                ))}
              </select>
              {/* Dropdown chevron */}
              <svg
                className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none"
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </div>

            <Link
              href="/dashboard"
              className="btn-ghost"
            >
              {tc("back")}
            </Link>
          </div>
        </div>

        {error && (
          <div className="card-glass border-[var(--vault-negative)]/40 border text-red-300 rounded-lg p-4 mb-8 animate-fade-in-up">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-24 text-muted-foreground font-mono animate-fade-in">
            {tc("loading")}
          </div>
        ) : data ? (
          <div className="space-y-12">

            {/* ── Big Number + Progress ──────────────────────────── */}
            <section className="card-glass-accent p-8 md:p-10 animate-fade-in-up delay-1">
              {/* Headline number */}
              <div className="text-center mb-8">
                <div className="font-mono text-xs uppercase tracking-widest text-[var(--vault-text-tertiary)] mb-3">
                  {t("shortTermGainsYTD")} {year}
                </div>
                <div className={cn(
                  "font-data text-5xl md:text-6xl font-bold tracking-tight",
                  exceeded ? "text-[var(--vault-negative)]" : "text-primary"
                )}>
                  {exceeded
                    ? formatCurrency(gains, locale, "EUR")
                    : <>
                        <span className="text-[var(--vault-text-tertiary)] text-2xl md:text-3xl mr-1">{t("remaining")}</span>
                        {formatCurrency(remaining, locale, "EUR")}
                      </>
                  }
                </div>
                {exceeded && (
                  <div className="font-mono text-sm text-[var(--vault-negative)] mt-2 animate-fade-in">
                    {t("exceededBy")} {formatCurrency(gains - limit, locale, "EUR")}
                  </div>
                )}
              </div>

              {/* Progress bar */}
              <div className="max-w-2xl mx-auto">
                <FreigrenzeBar currentAmount={gains} limit={limit} currency="EUR" />
              </div>

              {/* Exceeded alert */}
              {exceeded && (
                <div className="mt-6 card-glass border border-[var(--vault-negative)]/40 rounded-lg p-4 flex items-center gap-3 animate-fade-in-up delay-2">
                  <div className="shrink-0 w-10 h-10 rounded-full bg-[var(--vault-negative)]/15 flex items-center justify-center">
                    <svg className="w-5 h-5 text-[var(--vault-negative)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <div>
                    <div className="font-mono text-sm font-semibold text-[var(--vault-negative)]">
                      {t("exceededTitle")}
                    </div>
                    <div className="text-sm text-[var(--vault-text-secondary)]">
                      {t("exceededDesc")}
                    </div>
                  </div>
                </div>
              )}
            </section>

            {/* ── Cliff Visualization ────────────────────────────── */}
            <section className="animate-fade-in-up delay-2">
              <h2 className="font-display text-xl md:text-2xl font-bold mb-2">
                {t("cliffTitle")}
              </h2>
              <p className="text-sm text-[var(--vault-text-secondary)] font-sans mb-8 max-w-2xl">
                {t("cliffExplanation")}
              </p>

              <div className="grid md:grid-cols-[1fr,auto,1fr] gap-4 md:gap-0 items-stretch">
                {/* Left - Under limit (green) */}
                <div className="card-glass border-[var(--vault-positive)]/20 rounded-lg p-6 md:rounded-r-none">
                  <div className="flex items-center gap-2 mb-4">
                    <svg className="w-5 h-5 text-[var(--vault-positive)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="font-mono text-sm font-semibold text-[var(--vault-positive)]">
                      {t("underLimit")}
                    </span>
                  </div>
                  <div className="font-data text-3xl font-bold text-[var(--vault-positive)] mb-1">
                    {formatCurrency(999, locale, "EUR")}
                  </div>
                  <div className="text-xs text-[var(--vault-text-tertiary)] font-mono mb-4">
                    {t("gainsLabel")}
                  </div>
                  <div className="divider-accent mb-4" style={{ background: 'linear-gradient(90deg, transparent, oklch(0.72 0.19 155 / 40%), transparent)' }} />
                  <div className="text-xs text-[var(--vault-text-tertiary)] font-mono mb-1">
                    {t("taxOwed")}
                  </div>
                  <div className="font-data text-4xl md:text-5xl font-bold text-[var(--vault-positive)]">
                    {formatCurrency(0, locale, "EUR")}
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-[var(--vault-positive)]/80 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-[var(--vault-positive)] inline-block" />
                    {t("fullyExempt")}
                  </div>
                </div>

                {/* Center cliff divider */}
                <div className="hidden md:flex flex-col items-center justify-center px-4 relative">
                  <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-px bg-gradient-to-b from-[var(--vault-positive)]/40 via-[var(--vault-negative)]/60 to-[var(--vault-negative)]/40" />
                  <div className="relative z-10 bg-[var(--vault-bg-deep)] border border-[var(--vault-negative)]/40 rounded-full p-3">
                    <svg className="w-5 h-5 text-[var(--vault-negative)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
                    </svg>
                  </div>
                  <div className="relative z-10 font-mono text-[10px] font-bold text-[var(--vault-negative)] mt-1 uppercase tracking-widest">
                    {t("cliffLabel")}
                  </div>
                </div>

                {/* Mobile cliff divider */}
                <div className="flex md:hidden items-center justify-center py-2">
                  <div className="w-16 h-px bg-[var(--vault-negative)]/40" />
                  <div className="mx-3 bg-[var(--vault-bg-deep)] border border-[var(--vault-negative)]/40 rounded-full p-2">
                    <svg className="w-4 h-4 text-[var(--vault-negative)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                    </svg>
                  </div>
                  <div className="w-16 h-px bg-[var(--vault-negative)]/40" />
                </div>

                {/* Right - Over limit (red) */}
                <div className="card-glass border-[var(--vault-negative)]/30 rounded-lg p-6 md:rounded-l-none">
                  <div className="flex items-center gap-2 mb-4">
                    <svg className="w-5 h-5 text-[var(--vault-negative)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span className="font-mono text-sm font-semibold text-[var(--vault-negative)]">
                      {t("overLimit")}
                    </span>
                  </div>
                  <div className="font-data text-3xl font-bold text-[var(--vault-negative)] mb-1">
                    {formatCurrency(1001, locale, "EUR")}
                  </div>
                  <div className="text-xs text-[var(--vault-text-tertiary)] font-mono mb-4">
                    {t("gainsLabel")}
                  </div>
                  <div className="divider-accent mb-4" style={{ background: 'linear-gradient(90deg, transparent, oklch(0.65 0.22 25 / 40%), transparent)' }} />
                  <div className="text-xs text-[var(--vault-text-tertiary)] font-mono mb-1">
                    {t("taxOwed")}
                  </div>
                  <div className="font-data text-4xl md:text-5xl font-bold text-[var(--vault-negative)]">
                    ~{formatCurrency(Math.round(1001 * taxRate), locale, "EUR")}
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-[var(--vault-negative)]/80 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-[var(--vault-negative)] inline-block" />
                    {t("fullTax")}
                  </div>
                </div>
              </div>
            </section>

            {/* ── Info Cards ─────────────────────────────────────── */}
            <section className="grid md:grid-cols-3 gap-4 animate-fade-in-up delay-3">
              {/* Realized gains */}
              <div className="card-glass p-6">
                <div className="font-mono text-xs uppercase tracking-widest text-[var(--vault-text-tertiary)] mb-3">
                  {t("realizedGains")}
                </div>
                <div className={cn(
                  "font-data text-2xl md:text-3xl font-bold",
                  exceeded ? "text-[var(--vault-negative)]" : "text-[var(--vault-positive)]"
                )}>
                  {formatCurrency(data.realized_gains_ytd, locale, "EUR")}
                </div>
              </div>

              {/* Headroom */}
              <div className="card-glass p-6">
                <div className="font-mono text-xs uppercase tracking-widest text-[var(--vault-text-tertiary)] mb-3">
                  {t("headroom")}
                </div>
                <div className={cn(
                  "font-data text-2xl md:text-3xl font-bold",
                  exceeded ? "text-[var(--vault-negative)]" : "text-primary"
                )}>
                  {exceeded
                    ? formatCurrency(0, locale, "EUR")
                    : formatCurrency(data.remaining_headroom, locale, "EUR")}
                </div>
              </div>

              {/* Projected tax */}
              <div className="card-glass p-6">
                <div className="font-mono text-xs uppercase tracking-widest text-[var(--vault-text-tertiary)] mb-3">
                  {t("projectedTax")}
                </div>
                <div className={cn(
                  "font-data text-2xl md:text-3xl font-bold",
                  exceeded ? "text-[var(--vault-negative)]" : "text-[var(--vault-positive)]"
                )}>
                  {exceeded
                    ? `~${formatCurrency(data.projected_tax_if_exceeded, locale, "EUR")}`
                    : formatCurrency(0, locale, "EUR")}
                </div>
              </div>
            </section>

            {/* ── Disclaimer ─────────────────────────────────────── */}
            <section className="animate-fade-in-up delay-4">
              <div className="glass rounded-lg p-5">
                <p className="font-mono text-xs font-semibold text-[var(--vault-text-secondary)] mb-1.5">
                  {t("disclaimerTitle")}
                </p>
                <p className="font-mono text-xs text-[var(--vault-text-tertiary)] leading-relaxed">
                  {t("disclaimerText")}
                </p>
              </div>
            </section>
          </div>
        ) : null}
      </div>
    </div>
  );
}
