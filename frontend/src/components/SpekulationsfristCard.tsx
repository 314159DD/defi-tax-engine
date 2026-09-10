"use client";

import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import { formatCurrency, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface SpekulationsfristCardProps {
  token: string;
  amount: string;
  acquisitionDate: string;
  daysRemaining: number;
  currentValue: string;
  unrealizedGain: string;
  taxIfSoldNow: string;
  spekulationsfristEnd: string;
}

function getStatusInfo(daysRemaining: number) {
  if (daysRemaining <= 0)
    return { borderColor: "border-l-[var(--vault-positive)]", strokeColor: "var(--vault-positive)", label: "exempt" as const };
  if (daysRemaining <= 90)
    return { borderColor: "border-l-[var(--vault-negative)]", strokeColor: "var(--vault-negative)", label: "taxable" as const };
  if (daysRemaining <= 270)
    return { borderColor: "border-l-[var(--vault-warning)]", strokeColor: "var(--vault-warning)", label: "approaching" as const };
  return { borderColor: "border-l-primary", strokeColor: "var(--vault-accent)", label: "taxable" as const };
}

function getProgressPercent(daysRemaining: number): number {
  const elapsed = 365 - Math.max(0, daysRemaining);
  return Math.min(100, Math.max(0, (elapsed / 365) * 100));
}

export function SpekulationsfristCard({
  token,
  amount,
  acquisitionDate,
  daysRemaining,
  currentValue,
  unrealizedGain,
  taxIfSoldNow,
  spekulationsfristEnd,
}: SpekulationsfristCardProps) {
  const t = useTranslations("spekulationsfrist");
  const locale = useLocale();

  const { borderColor, strokeColor } = getStatusInfo(daysRemaining);
  const progress = getProgressPercent(daysRemaining);
  const isExempt = daysRemaining <= 0;
  const gain = parseFloat(unrealizedGain);

  // SVG ring params
  const size = 64;
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  return (
    <div
      className={cn(
        "card-glass border-l-4 flex items-start gap-4 p-5 transition-transform hover:scale-[1.01]",
        borderColor
      )}
    >
      {/* SVG circular progress ring */}
      <div className="shrink-0">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--border)"
            strokeWidth="4"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={strokeColor}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            className="transition-all duration-700"
          />
          <text
            x={size / 2}
            y={size / 2}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-foreground font-mono"
            fontSize="13"
            fontWeight="600"
          >
            {isExempt ? "\u2713" : `${daysRemaining}d`}
          </text>
        </svg>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Top: Token + amount */}
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <span className="font-mono font-semibold text-base">{token}</span>
            <span className="font-data text-sm text-muted-foreground">
              {parseFloat(amount).toLocaleString(locale === "de" ? "de-DE" : "en-US", { maximumFractionDigits: 6 })}
            </span>
          </div>
          {isExempt && (
            <span className="font-mono text-[10px] uppercase tracking-wider bg-[var(--vault-accent)]/20 text-[var(--vault-accent)] px-2 py-0.5 rounded">
              {t("taxFree")}
            </span>
          )}
        </div>

        {/* Acquisition date */}
        <div className="text-xs text-muted-foreground font-sans mb-2">
          {t("acquired")}: {formatDate(acquisitionDate, locale)}
          {!isExempt && (
            <span className="ml-2 font-data">
              - {t("daysRemaining", { days: daysRemaining })}
            </span>
          )}
        </div>

        {/* Bottom row: value + gain */}
        <div className="flex items-baseline justify-between">
          <div>
            <div className="font-data text-lg font-semibold">
              {formatCurrency(currentValue, locale)}
            </div>
          </div>
          <div className="text-right">
            <div
              className={cn(
                "font-data text-sm font-medium",
                gain >= 0 ? "text-[var(--vault-positive)]" : "text-[var(--vault-negative)]"
              )}
            >
              {gain >= 0 ? "+" : ""}
              {formatCurrency(unrealizedGain, locale)}
            </div>
            {!isExempt && parseFloat(taxIfSoldNow) > 0 && (
              <div className="text-[10px] text-muted-foreground font-sans mt-0.5">
                {t("taxIfSoldNow")}: <span className="font-data text-[var(--vault-negative)]">{formatCurrency(taxIfSoldNow, locale)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Exempt message */}
        {isExempt && (
          <div className="mt-2 text-xs text-[var(--vault-positive)] font-sans flex items-center gap-1.5">
            <svg className="size-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {t("exemptSince", { date: formatDate(spekulationsfristEnd, locale) })}
          </div>
        )}
      </div>
    </div>
  );
}
