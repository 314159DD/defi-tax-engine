"use client";

import { useEffect, useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import { Button } from "@/components/ui/button";
import { SpekulationsfristCard } from "@/components/SpekulationsfristCard";
import type { SpekulationsfristLot } from "@/lib/api";
import { db } from "@/db/index";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

type SortMode = "soonest" | "largest_value" | "token_name";

// Demo data for when backend isn't returning real data yet
const MOCK_LOTS: SpekulationsfristLot[] = [
  {
    token: "ETH",
    amount: "2.5",
    acquisition_date: "2025-06-15",
    days_remaining: 81,
    status: "taxable",
    current_value: "8750.00",
    unrealized_gain: "2125.00",
    tax_if_sold_now: "956.25",
    spekulationsfrist_end: "2026-06-15",
  },
  {
    token: "BTC",
    amount: "0.15",
    acquisition_date: "2025-01-10",
    days_remaining: 0,
    status: "exempt",
    current_value: "13050.00",
    unrealized_gain: "4200.00",
    tax_if_sold_now: "0",
    spekulationsfrist_end: "2026-01-10",
  },
  {
    token: "ETH",
    amount: "1.0",
    acquisition_date: "2025-09-20",
    days_remaining: 178,
    status: "approaching",
    current_value: "3500.00",
    unrealized_gain: "800.00",
    tax_if_sold_now: "360.00",
    spekulationsfrist_end: "2026-09-20",
  },
  {
    token: "SOL",
    amount: "50",
    acquisition_date: "2025-11-01",
    days_remaining: 220,
    status: "approaching",
    current_value: "7500.00",
    unrealized_gain: "1500.00",
    tax_if_sold_now: "675.00",
    spekulationsfrist_end: "2026-11-01",
  },
  {
    token: "MATIC",
    amount: "5000",
    acquisition_date: "2026-01-15",
    days_remaining: 295,
    status: "approaching",
    current_value: "4250.00",
    unrealized_gain: "-750.00",
    tax_if_sold_now: "0",
    spekulationsfrist_end: "2027-01-15",
  },
  {
    token: "BTC",
    amount: "0.05",
    acquisition_date: "2026-03-01",
    days_remaining: 340,
    status: "taxable",
    current_value: "4350.00",
    unrealized_gain: "150.00",
    tax_if_sold_now: "67.50",
    spekulationsfrist_end: "2027-03-01",
  },
  {
    token: "ARB",
    amount: "2000",
    acquisition_date: "2025-04-10",
    days_remaining: 15,
    status: "taxable",
    current_value: "1800.00",
    unrealized_gain: "600.00",
    tax_if_sold_now: "270.00",
    spekulationsfrist_end: "2026-04-10",
  },
  {
    token: "ETH",
    amount: "0.8",
    acquisition_date: "2025-07-30",
    days_remaining: 126,
    status: "approaching",
    current_value: "2800.00",
    unrealized_gain: "560.00",
    tax_if_sold_now: "252.00",
    spekulationsfrist_end: "2026-07-30",
  },
];

function sortLots(lots: SpekulationsfristLot[], mode: SortMode): SpekulationsfristLot[] {
  const sorted = [...lots];
  switch (mode) {
    case "soonest":
      return sorted.sort((a, b) => {
        if (a.days_remaining <= 0 && b.days_remaining > 0) return 1;
        if (b.days_remaining <= 0 && a.days_remaining > 0) return -1;
        return a.days_remaining - b.days_remaining;
      });
    case "largest_value":
      return sorted.sort((a, b) => parseFloat(b.current_value) - parseFloat(a.current_value));
    case "token_name":
      return sorted.sort((a, b) => a.token.localeCompare(b.token));
    default:
      return sorted;
  }
}

export default function SpekulationsfristPage() {
  const t = useTranslations("spekulationsfrist");
  const tc = useTranslations("common");
  const locale = useLocale();

  const [lots, setLots] = useState<SpekulationsfristLot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("soonest");

  useEffect(() => {
    setLoading(true);
    db.taxLots
      .toArray()
      .then((dbLots) => {
        if (dbLots.length === 0) {
          setLots(MOCK_LOTS);
        } else {
          const now = new Date();
          setLots(dbLots.filter(l => parseFloat(l.remaining) > 0).map((l) => {
            const acquired = new Date(l.acquisitionDate);
            const endDate = new Date(acquired.getTime() + 366 * 86_400_000);
            const daysRemaining = Math.max(0, Math.ceil((endDate.getTime() - now.getTime()) / 86_400_000));
            return {
              token: l.token,
              amount: l.amount,
              acquisition_date: l.acquisitionDate,
              days_remaining: daysRemaining,
              status: daysRemaining <= 0 ? "exempt" as const : daysRemaining <= 90 ? "approaching" as const : "taxable" as const,
              current_value: "0", // price lookup not yet wired
              unrealized_gain: "0",
              tax_if_sold_now: "0",
              spekulationsfrist_end: endDate.toISOString().slice(0, 10),
            };
          }));
        }
        setError(null);
      })
      .catch(() => {
        setLots(MOCK_LOTS);
        setError(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const sortedLots = useMemo(() => sortLots(lots, sortMode), [lots, sortMode]);

  const stats = useMemo(() => {
    const exempt = lots.filter((l) => l.days_remaining <= 0).length;
    const approaching = lots.filter((l) => l.days_remaining > 0 && l.days_remaining <= 270).length;
    const taxable = lots.filter((l) => l.days_remaining > 270).length;
    return { exempt, approaching, taxable };
  }, [lots]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between animate-fade-in-up">
        <div>
          <h1 className="font-display text-2xl font-semibold">{t("title")}</h1>
          <p className="text-muted-foreground text-sm font-sans mt-1">{t("subtitle")}</p>
        </div>
        <Button variant="outline" size="sm" className="font-mono text-xs" render={<Link href="/dashboard" />}>
          {tc("back")}
        </Button>
      </div>

      {error && (
        <div className="glass rounded-lg p-4 border-[var(--vault-negative)]/30 text-[var(--vault-negative)]">
          {error}
        </div>
      )}

      {/* Summary strip */}
      <div className="glass rounded-lg px-5 py-3 flex items-center gap-6 flex-wrap animate-fade-in-up delay-1">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-[var(--vault-positive)]" />
          <span className="font-data text-lg font-semibold text-[var(--vault-positive)]">{stats.exempt}</span>
          <span className="text-xs text-muted-foreground font-sans">{t("taxFreeLots")}</span>
        </div>
        <div className="w-px h-5 bg-border" />
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-[var(--vault-warning)]" />
          <span className="font-data text-lg font-semibold text-[var(--vault-warning)]">{stats.approaching}</span>
          <span className="text-xs text-muted-foreground font-sans">{t("approachingLots")}</span>
        </div>
        <div className="w-px h-5 bg-border" />
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-[var(--vault-negative)]" />
          <span className="font-data text-lg font-semibold text-[var(--vault-negative)]">{stats.taxable}</span>
          <span className="text-xs text-muted-foreground font-sans">{t("taxableLots")}</span>
        </div>
      </div>

      {/* Sort controls */}
      <div className="flex items-center gap-1 animate-fade-in-up delay-2">
        {([
          { mode: "soonest" as SortMode, label: t("sortSoonest") },
          { mode: "largest_value" as SortMode, label: t("sortLargestValue") },
          { mode: "token_name" as SortMode, label: t("sortTokenName") },
        ]).map(({ mode, label }) => (
          <button
            key={mode}
            onClick={() => setSortMode(mode)}
            className={cn(
              "px-3 py-1.5 text-xs font-mono rounded-md transition-colors",
              sortMode === mode
                ? "text-primary border-b-2 border-primary bg-primary/5"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Lot cards grid */}
      {loading ? (
        <div className="text-center py-12 text-muted-foreground font-sans">{tc("loading")}</div>
      ) : lots.length === 0 ? (
        <div className="card-glass p-8 text-center">
          <p className="text-muted-foreground font-sans mb-3">{t("noLots")}</p>
          <Button className="btn-primary" render={<Link href="/wallets" />}>
            {t("importFirst")}
          </Button>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {sortedLots.map((lot, idx) => (
            <div key={`${lot.token}-${lot.acquisition_date}-${idx}`} className={cn("animate-fade-in-up", `delay-${Math.min(idx + 3, 8)}`)}>
              <SpekulationsfristCard
                token={lot.token}
                amount={lot.amount}
                acquisitionDate={lot.acquisition_date}
                daysRemaining={lot.days_remaining}
                currentValue={lot.current_value}
                unrealizedGain={lot.unrealized_gain}
                taxIfSoldNow={lot.tax_if_sold_now}
                spekulationsfristEnd={lot.spekulationsfrist_end}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
