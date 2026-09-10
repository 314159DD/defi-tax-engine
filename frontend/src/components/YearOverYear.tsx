"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { calculate, type TaxSummary } from "@/lib/api";

function fmt(val: string): string {
  const n = parseFloat(val);
  if (isNaN(n)) return "$0.00";
  const abs = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return n < 0 ? `-$${abs}` : `$${abs}`;
}

function delta(current: string, previous: string): { pct: number; sign: string; color: string } {
  const c = parseFloat(current);
  const p = parseFloat(previous);
  if (isNaN(c) || isNaN(p) || p === 0) return { pct: 0, sign: "", color: "" };
  const pct = ((c - p) / Math.abs(p)) * 100;
  return {
    pct: Math.abs(pct),
    sign: pct >= 0 ? "+" : "-",
    color: pct > 0 ? "text-red-400" : "text-green-400",
  };
}

interface Row {
  labelKey: string;
  key: keyof TaxSummary;
  higherIsBetter: boolean;
}

const ROWS: Row[] = [
  { labelKey: "totalGains", key: "total_gains", higherIsBetter: false },
  { labelKey: "totalLosses", key: "total_losses", higherIsBetter: true },
  { labelKey: "netGainLoss", key: "net_gain_loss", higherIsBetter: false },
  { labelKey: "estTax", key: "estimated_tax", higherIsBetter: false },
];

export function YearOverYear({ method = "FIFO" }: { method?: string }) {
  const t = useTranslations("yearOverYear");
  const tc = useTranslations("common");

  const currentYear = new Date().getFullYear();
  const prevYear = currentYear - 1;

  const [current, setCurrent] = useState<TaxSummary | null>(null);
  const [previous, setPrevious] = useState<TaxSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([calculate.summary(currentYear, method), calculate.summary(prevYear, method)])
      .then(([c, p]) => {
        setCurrent(c);
        setPrevious(p);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [method, currentYear, prevYear]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{t("title")}</CardTitle>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="text-sm text-red-400">{error}</p>
        )}
        {loading && <p className="text-sm text-muted-foreground">{tc("loading")}</p>}
        {!loading && !error && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 pr-4 font-medium text-muted-foreground">{t("metric")}</th>
                  <th className="text-right py-2 px-2 font-medium text-muted-foreground">{prevYear}</th>
                  <th className="text-right py-2 px-2 font-medium text-muted-foreground">{currentYear}</th>
                  <th className="text-right py-2 pl-2 font-medium text-muted-foreground">{t("change")}</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map(({ labelKey, key }) => {
                  const curVal = current ? String(current[key]) : "0";
                  const prevVal = previous ? String(previous[key]) : "0";
                  const d = delta(curVal, prevVal);
                  const curNum = parseFloat(curVal);

                  return (
                    <tr key={key} className="border-b border-border/50 last:border-0">
                      <td className="py-2 pr-4 text-muted-foreground">{t(labelKey)}</td>
                      <td className="text-right px-2 tabular-nums">
                        {previous ? fmt(prevVal) : "-"}
                      </td>
                      <td className={`text-right px-2 tabular-nums font-medium ${curNum > 0 ? "text-green-400" : curNum < 0 ? "text-red-400" : ""}`}>
                        {current ? fmt(curVal) : "-"}
                      </td>
                      <td className={`text-right pl-2 tabular-nums text-xs ${d.color}`}>
                        {d.pct > 0 ? `${d.sign}${d.pct.toFixed(1)}%` : "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="text-xs text-muted-foreground mt-3">
              {t("disclaimer", { method })}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
