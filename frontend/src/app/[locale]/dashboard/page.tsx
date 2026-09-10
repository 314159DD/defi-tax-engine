"use client";

import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FreigrenzeBar } from "@/components/FreigrenzeBar";
import type { Wallet } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { localWallets, getAllSerializedTransactions, getKnownWallets } from "@/lib/local-api";
import { useTaxEngine } from "@/hooks/useTaxEngine";

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2];

function fmtSigned(val: string, locale: string, currency?: string): string {
  const n = parseFloat(val);
  if (isNaN(n)) return formatCurrency(0, locale, currency);
  const prefix = n > 0 ? "+" : "";
  return `${prefix}${formatCurrency(n, locale, currency)}`;
}

function valueColor(val: string): string {
  const n = parseFloat(val);
  if (n > 0) return "text-[var(--vault-positive)]";
  if (n < 0) return "text-[var(--vault-negative)]";
  return "text-foreground";
}

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const tc = useTranslations("common");
  const locale = useLocale();

  const [year, setYear] = useState(CURRENT_YEAR);
  const [method, setMethod] = useState("FIFO");
  const [walletList, setWalletList] = useState<Wallet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const engine = useTaxEngine();

  // Load wallets from IndexedDB, then trigger Worker calculation
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        const [w, txs, kw] = await Promise.all([
          localWallets.list(),
          getAllSerializedTransactions(),
          getKnownWallets(),
        ]);
        if (cancelled) return;
        setWalletList(w);

        if (txs.length > 0) {
          const country = locale === "de" ? "DE" : "US";
          engine.calculate(
            txs,
            method as "FIFO" | "LIFO" | "HIFO",
            country as "US" | "DE",
            year,
            kw,
          );
        } else {
          setLoading(false);
        }
        setError(null);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      }
    })();

    return () => { cancelled = true; };
  }, [year, method, locale]); // eslint-disable-line react-hooks/exhaustive-deps

  // When Worker finishes, stop loading
  useEffect(() => {
    if (engine.status === "done" || engine.status === "error") {
      setLoading(false);
      if (engine.error) setError(engine.error);
    }
  }, [engine.status, engine.error]);

  // Adapt Worker result to dashboard display format
  const summary = engine.result
    ? {
        year,
        method,
        total_gains: engine.result.summary.totalGains,
        total_losses: engine.result.summary.totalLosses,
        net_gain_loss: engine.result.summary.net,
        short_term: engine.result.summary.shortTermGains,
        long_term: engine.result.summary.longTermGains,
        estimated_tax: engine.result.summary.taxLiability,
        transaction_count: engine.result.disposals.length,
      }
    : null;

  const cur = locale === "de" ? "EUR" : "USD";

  // YoY bars
  const currentNet = summary ? parseFloat(summary.net_gain_loss) : 0;
  const prevNet = 0; // placeholder until YoY endpoint is loaded separately
  const maxBar = Math.max(Math.abs(currentNet), Math.abs(prevNet), 1);

  // Spek stats - derived from Worker lots
  const spekExempt = engine.result?.lots.filter((l) => {
    const acquired = new Date(l.acquisitionDate);
    const now = new Date();
    return (now.getTime() - acquired.getTime()) / 86_400_000 > 365;
  }).length ?? 0;
  const spekApproaching = engine.result?.lots.filter((l) => {
    const acquired = new Date(l.acquisitionDate);
    const now = new Date();
    const days = (now.getTime() - acquired.getTime()) / 86_400_000;
    return days > 95 && days <= 365;
  }).length ?? 0;

  // Freigrenze stats - derived from Worker disposals (short-term gains)
  const fgGains = engine.result?.disposals
    .filter((d) => d.holdingPeriod === "short-term" && parseFloat(d.gainLossUsd) > 0)
    .reduce((sum, d) => sum + parseFloat(d.gainLossUsd), 0) ?? 0;
  const fgLimit = 1000;
  const fgRemaining = Math.max(0, fgLimit - fgGains);

  return (
    <div className="space-y-8">
      {/* Top controls bar */}
      <div className="glass rounded-lg px-4 py-3 flex items-center justify-between animate-fade-in-up">
        <h1 className="font-display text-xl font-semibold">{t("title")}</h1>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground font-sans uppercase tracking-wider">
              {tc("year")}
            </span>
            <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
              <SelectTrigger className="w-24 h-8 font-mono text-sm glass border-white/10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {YEARS.map((y) => (
                  <SelectItem key={y} value={String(y)} className="font-mono">
                    {y}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground font-sans uppercase tracking-wider">
              {tc("method")}
            </span>
            <Select value={method} onValueChange={(v) => v && setMethod(v)}>
              <SelectTrigger className="w-20 h-8 font-mono text-sm glass border-white/10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["FIFO", "LIFO", "HIFO"].map((m) => (
                  <SelectItem key={m} value={m} className="font-mono">
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="text-lg leading-none">{locale === "de" ? "🇩🇪" : "🇺🇸"}</div>
        </div>
      </div>

      {error && (
        <div className="glass rounded-lg p-4 border-[var(--vault-negative)]/30 text-[var(--vault-negative)]">
          {error}
        </div>
      )}

      {/* Key metrics - asymmetric layout */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Net Gain/Loss - hero card */}
        <div className="md:col-span-2 card-glass-accent p-6 animate-fade-in-up delay-1">
          <div className="text-xs font-sans uppercase tracking-wider text-muted-foreground mb-2">
            {t("netGainLoss")}
          </div>
          <div
            className={cn(
              "font-data text-4xl md:text-5xl font-bold animate-count-up",
              loading ? "text-muted-foreground" : valueColor(summary?.net_gain_loss ?? "0")
            )}
          >
            {loading ? "---" : fmtSigned(summary?.net_gain_loss ?? "0", locale, cur)}
          </div>
          <div className="mt-3 flex gap-4 text-sm text-muted-foreground font-sans">
            <span>
              {t("shortTerm")}:{" "}
              <span className={cn("font-data", valueColor(summary?.short_term ?? "0"))}>
                {loading ? "---" : formatCurrency(summary?.short_term ?? "0", locale, cur)}
              </span>
            </span>
            <span>
              {t("longTerm")}:{" "}
              <span className={cn("font-data", valueColor(summary?.long_term ?? "0"))}>
                {loading ? "---" : formatCurrency(summary?.long_term ?? "0", locale, cur)}
              </span>
            </span>
          </div>
        </div>

        {/* Effective Rate */}
        <div className="card-glass p-6 animate-fade-in-up delay-2">
          <div className="text-xs font-sans uppercase tracking-wider text-muted-foreground mb-2">
            {t("estTax")}
          </div>
          <div className={cn("font-data text-3xl font-bold animate-count-up delay-2", loading ? "text-muted-foreground" : "text-[var(--vault-warning)]")}>
            {loading ? "---" : formatCurrency(summary?.estimated_tax ?? "0", locale, cur)}
          </div>
        </div>
      </div>

      {/* Second row - three smaller cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {([
          { label: t("totalGains"), value: summary?.total_gains ?? "0", colorClass: "text-[var(--vault-positive)]", raw: false },
          { label: t("totalLosses"), value: summary?.total_losses ?? "0", colorClass: "text-[var(--vault-negative)]", raw: false },
          { label: t("txCount"), value: String(summary?.transaction_count ?? 0), colorClass: "text-foreground", raw: true },
        ] as { label: string; value: string; colorClass: string; raw: boolean }[]).map(({ label, value, colorClass, raw }, i) => (
          <div key={label} className={cn("card-glass p-5 animate-fade-in-up", `delay-${i + 3}`)}>
            <div className="text-xs font-sans uppercase tracking-wider text-muted-foreground mb-1">
              {label}
            </div>
            <div className={cn("font-data text-2xl font-semibold animate-count-up", `delay-${i + 3}`, loading ? "text-muted-foreground" : colorClass)}>
              {loading ? "---" : raw ? value : formatCurrency(value, locale, cur)}
            </div>
          </div>
        ))}
      </div>

      {/* YoY comparison bars */}
      {summary && (
        <div className="card-glass p-6 animate-fade-in-up delay-5">
          <div className="text-xs font-sans uppercase tracking-wider text-muted-foreground mb-4">
            {t("yoyComparison")}
          </div>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs w-12 text-right text-muted-foreground">{year - 1}</span>
              <div className="flex-1 h-6 rounded bg-[var(--vault-bg-elevated)] overflow-hidden">
                <div
                  className="h-full rounded bg-[var(--vault-accent-dim)] transition-all duration-700"
                  style={{ width: `${Math.abs(prevNet) / maxBar * 100}%` }}
                />
              </div>
              <span className="font-data text-xs w-24 text-right text-muted-foreground">
                {formatCurrency(prevNet, locale, cur)}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs w-12 text-right">{year}</span>
              <div className="flex-1 h-6 rounded bg-[var(--vault-bg-elevated)] overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded transition-all duration-700",
                    currentNet >= 0 ? "bg-[var(--vault-accent)]" : "bg-[var(--vault-negative)]"
                  )}
                  style={{ width: `${Math.abs(currentNet) / maxBar * 100}%` }}
                />
              </div>
              <span className={cn("font-data text-xs w-24 text-right", valueColor(summary.net_gain_loss))}>
                {fmtSigned(summary.net_gain_loss, locale, cur)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* German tax widgets - two side by side */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Spekulationsfrist mini */}
        <div className="card-glass p-5 animate-fade-in-up delay-6">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-sans uppercase tracking-wider text-muted-foreground">
              {t("spekulationsfristWidget")}
            </div>
            <Button variant="outline" size="sm" className="h-7 text-xs font-mono" render={<Link href="/dashboard/spekulationsfrist" />}>
              {t("viewSpekulationsfrist")}
            </Button>
          </div>
          <div className="flex items-center gap-4">
            {/* Mini ring */}
            <svg width="56" height="56" viewBox="0 0 56 56" className="shrink-0">
              <circle cx="28" cy="28" r="24" fill="none" stroke="var(--border)" strokeWidth="4" />
              <circle
                cx="28" cy="28" r="24"
                fill="none"
                stroke="var(--vault-positive)"
                strokeWidth="4"
                strokeDasharray={`${(spekExempt / Math.max(spekExempt + spekApproaching, 1)) * 150.8} 150.8`}
                strokeLinecap="round"
                transform="rotate(-90 28 28)"
                className="transition-all duration-700"
              />
              <text x="28" y="31" textAnchor="middle" className="fill-foreground font-mono text-xs" fontSize="12" fontWeight="600">
                {spekExempt}
              </text>
            </svg>
            <div>
              <div className="font-data text-lg">
                <span className="text-[var(--vault-positive)]">{spekExempt}</span>
                <span className="text-muted-foreground text-sm font-sans"> {t("lotsTaxFree")}</span>
              </div>
              <div className="font-data text-sm text-[var(--vault-warning)]">
                {spekApproaching} <span className="text-muted-foreground text-xs font-sans">{t("lotsApproaching")}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Freigrenze mini */}
        <div className="card-glass p-5 animate-fade-in-up delay-7">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-sans uppercase tracking-wider text-muted-foreground">
              {t("freigrenzeWidget")}
            </div>
            <Button variant="outline" size="sm" className="h-7 text-xs font-mono" render={<Link href="/dashboard/freigrenze" />}>
              {t("viewFreigrenze")}
            </Button>
          </div>
          <div className="space-y-2">
            <FreigrenzeBar currentAmount={fgGains} limit={fgLimit} currency={cur} />
            <div className="text-sm font-sans text-muted-foreground">
              <span className="font-data text-[var(--vault-warning)]">{formatCurrency(fgRemaining, locale, cur)}</span>{" "}
              {t("remainingOnFreigrenze")}
            </div>
          </div>
        </div>
      </div>

      {/* Recent activity */}
      {walletList.length > 0 && (
        <div className="card-glass p-5 animate-fade-in-up delay-8">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-sans uppercase tracking-wider text-muted-foreground">
              {t("walletsCount", { count: walletList.length })}
            </div>
            <Button variant="outline" size="sm" className="h-7 text-xs font-mono" render={<Link href="/wallets" />}>
              {t("manageWallets")}
            </Button>
          </div>
          <div className="space-y-1">
            {walletList.slice(0, 5).map((w) => (
              <div
                key={w.id}
                className="flex items-center justify-between py-2 px-3 rounded-md hover:bg-white/[0.03] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "w-2 h-2 rounded-full",
                    w.import_status?.status === "done" ? "bg-[var(--vault-positive)]" :
                    w.import_status?.status === "running" ? "bg-[var(--vault-warning)]" :
                    w.import_status?.status === "error" ? "bg-[var(--vault-negative)]" :
                    "bg-muted-foreground"
                  )} />
                  <span className="font-mono text-sm truncate max-w-[200px] md:max-w-[320px]">
                    {w.label || w.address}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="font-mono text-xs capitalize">
                    {w.chain}
                  </Badge>
                  <ImportBadge status={w.import_status?.status} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {walletList.length === 0 && !loading && (
        <div className="card-glass p-8 text-center animate-fade-in-up delay-6">
          <p className="text-muted-foreground font-sans mb-3">{t("noWallets")}</p>
          <Button className="btn-primary" render={<Link href="/wallets" />}>
            {t("addFirstWallet")}
          </Button>
        </div>
      )}

      {/* Quick links */}
      <div className="flex gap-3 flex-wrap animate-fade-in-up delay-8">
        <Button className="btn-primary" render={<Link href="/reports" />}>
          {t("downloadReports")}
        </Button>
        <Button className="btn-ghost" render={<Link href="/transactions" />}>
          {t("viewTransactions")}
        </Button>
      </div>
    </div>
  );
}

function ImportBadge({ status }: { status?: string }) {
  const t = useTranslations("dashboard");
  if (!status || status === "not_started")
    return <Badge variant="secondary" className="font-mono text-[10px]">{t("notImported")}</Badge>;
  if (status === "running") return <Badge className="bg-[var(--vault-warning)] text-black font-mono text-[10px]">{t("importing")}</Badge>;
  if (status === "done") return <Badge className="bg-[var(--vault-positive)]/20 text-[var(--vault-positive)] font-mono text-[10px]">{t("imported")}</Badge>;
  return <Badge variant="destructive" className="font-mono text-[10px]">{t("importError")}</Badge>;
}
