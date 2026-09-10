"use client";

import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import { formatCurrency } from "@/lib/format";

interface FreigrenzeBarProps {
  currentAmount: number;
  limit: number;
  currency?: string;
}

function getBarColor(pct: number): string {
  if (pct >= 95) return "var(--vault-negative)";
  if (pct >= 70) return "var(--vault-warning)";
  return "var(--vault-positive)";
}

export function FreigrenzeBar({ currentAmount, limit, currency = "EUR" }: FreigrenzeBarProps) {
  const t = useTranslations("freigrenze");
  const locale = useLocale();

  const pct = limit > 0 ? (currentAmount / limit) * 100 : 0;
  const clampedPct = Math.min(pct, 100);
  const color = getBarColor(pct);

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="font-data text-sm" style={{ color }}>
          {formatCurrency(currentAmount, locale, currency)}
        </span>
        <span className="font-data text-xs text-muted-foreground">
          / {formatCurrency(limit, locale, currency)}
        </span>
      </div>
      <div className="relative w-full h-2 rounded-full bg-border overflow-hidden">
        {/* Fill with gradient based on percentage */}
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{
            width: `${clampedPct}%`,
            background: `linear-gradient(90deg, var(--vault-positive), ${color})`,
          }}
        />
        {/* Small marker at current position */}
        {clampedPct > 2 && clampedPct <= 100 && (
          <div
            className="absolute top-[-1px] w-1 h-[10px] rounded-full bg-white/80 transition-all duration-700"
            style={{ left: `calc(${clampedPct}% - 2px)` }}
          />
        )}
      </div>
    </div>
  );
}
