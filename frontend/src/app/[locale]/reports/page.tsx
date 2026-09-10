"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useTaxEngine } from "@/hooks/useTaxEngine";
import { getAllSerializedTransactions, getKnownWallets } from "@/lib/local-api";
import type { SerializedTaxSummary } from "@/engine";

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2];

function fmt(val?: string | null): string {
  if (!val) return "\u2014";
  const n = parseFloat(val);
  if (isNaN(n)) return "\u2014";
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function netColor(val?: string | null): string {
  if (!val) return "";
  const n = parseFloat(val);
  return n > 0 ? "text-green-400" : n < 0 ? "text-red-400" : "";
}

/* Report types per locale */
function getReportTypes(locale: string) {
  if (locale === "de") {
    return [
      { key: "form8949" as const, titleKey: "form8949Title" as const, descKey: "form8949Desc" as const },
      { key: "turbotax" as const, titleKey: "turbotaxTitle" as const, descKey: "turbotaxDesc" as const },
      { key: "schedule_d" as const, titleKey: "scheduleDTitle" as const, descKey: "scheduleDDesc" as const },
      { key: "json" as const, titleKey: "jsonTitle" as const, descKey: "jsonDesc" as const },
    ];
  }
  return [
    { key: "form8949" as const, titleKey: "form8949Title" as const, descKey: "form8949Desc" as const },
    { key: "turbotax" as const, titleKey: "turbotaxTitle" as const, descKey: "turbotaxDesc" as const },
    { key: "schedule_d" as const, titleKey: "scheduleDTitle" as const, descKey: "scheduleDDesc" as const },
    { key: "json" as const, titleKey: "jsonTitle" as const, descKey: "jsonDesc" as const },
  ];
}

export default function ReportsPage() {
  const t = useTranslations("reports");
  const tc = useTranslations("common");
  const locale = useLocale();

  const [year, setYear] = useState(CURRENT_YEAR);
  const [method, setMethod] = useState("FIFO");
  const [comparison, setComparison] = useState<Record<string, SerializedTaxSummary> | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"download" | "compare">("download");

  const engine = useTaxEngine();
  const reportWorkerRef = useRef<Worker | null>(null);

  // Run comparison on year change
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [txs, kw] = await Promise.all([
          getAllSerializedTransactions(),
          getKnownWallets(),
        ]);
        if (cancelled || txs.length === 0) return;
        const country = locale === "de" ? "DE" : "US";
        engine.compare(txs, year, country as "US" | "DE", kw);
      } catch {
        setComparison(null);
      }
    })();
    return () => { cancelled = true; };
  }, [year, locale]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pick up comparison results from engine
  useEffect(() => {
    if (engine.comparison) setComparison(engine.comparison);
  }, [engine.comparison]);

  const handleCalculate = async () => {
    setCalculating(true);
    setCalcError(null);
    try {
      const [txs, kw] = await Promise.all([
        getAllSerializedTransactions(),
        getKnownWallets(),
      ]);
      const country = locale === "de" ? "DE" : "US";
      engine.calculate(txs, method as "FIFO" | "LIFO" | "HIFO", country as "US" | "DE", year, kw);
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : String(e));
      setCalculating(false);
    }
  };

  // When calculate completes, also run compare
  useEffect(() => {
    if (engine.status === "done" && engine.result) {
      setCalculating(false);
      // Trigger comparison too
      (async () => {
        const [txs, kw] = await Promise.all([
          getAllSerializedTransactions(),
          getKnownWallets(),
        ]);
        const country = locale === "de" ? "DE" : "US";
        engine.compare(txs, year, country as "US" | "DE", kw);
      })();
    }
    if (engine.status === "error") {
      setCalculating(false);
      setCalcError(engine.error);
    }
  }, [engine.status]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Generate report client-side via Worker and trigger download. */
  const handleDownload = useCallback(async (reportType: string) => {
    if (!engine.result) {
      setCalcError("Run calculation first");
      return;
    }
    // Use a dedicated Worker for report generation
    const worker = new Worker(
      new URL("@/engine/worker.ts", import.meta.url),
      { type: "module" },
    );
    const country = locale === "de" ? "DE" : "US";
    worker.postMessage({
      type: "report",
      disposals: engine.result.disposals,
      incomeEvents: [], // TODO: pass income events if available
      year,
      method,
      country,
      reportType,
    });
    worker.onmessage = (e) => {
      if (e.data.type === "report-result") {
        for (const file of e.data.files) {
          const blob = new Blob([file.content], { type: file.mimeType });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = file.filename;
          a.click();
          URL.revokeObjectURL(url);
        }
        worker.terminate();
      } else if (e.data.type === "error") {
        setCalcError(e.data.message);
        worker.terminate();
      }
    };
  }, [engine.result, year, method, locale]);

  const reportTypes = getReportTypes(locale);

  return (
    <div className="max-w-4xl mx-auto px-4 py-12 md:py-20 space-y-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 animate-fade-in-up">
        <h1 className="font-display text-3xl md:text-4xl font-bold">{t("title")}</h1>

        {/* Year selector */}
        <select
          value={String(year)}
          onChange={(e) => setYear(Number(e.target.value))}
          className="glass rounded-md px-3 py-2 font-mono text-sm text-foreground border-none focus:outline-none focus:ring-2 focus:ring-primary/50 w-fit"
        >
          {YEARS.map((y) => (
            <option key={y} value={String(y)}>{y}</option>
          ))}
        </select>
      </div>

      {/* Controls */}
      <div className="flex gap-3 items-end flex-wrap animate-fade-in-up delay-1">
        <div>
          <p className="font-mono text-xs text-muted-foreground mb-1.5 uppercase tracking-wider">{tc("method")}</p>
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            className="bg-transparent border border-border rounded-md px-3 py-2 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            {["FIFO", "LIFO", "HIFO"].map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
        <button onClick={handleCalculate} disabled={calculating} className="btn-primary">
          {calculating ? t("calculating") : t("runCalculation")}
        </button>
      </div>

      {calcError && <p className="text-red-400 font-mono text-sm">{calcError}</p>}

      {/* Tabs */}
      <div className="animate-fade-in-up delay-2">
        <div className="flex gap-1 mb-6">
          <button
            onClick={() => setActiveTab("download")}
            className={`font-mono text-sm px-4 py-2 rounded-md transition-colors ${
              activeTab === "download"
                ? "bg-primary/10 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-white/5"
            }`}
          >
            {t("downloadReports")}
          </button>
          <button
            onClick={() => setActiveTab("compare")}
            className={`font-mono text-sm px-4 py-2 rounded-md transition-colors ${
              activeTab === "compare"
                ? "bg-primary/10 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-white/5"
            }`}
          >
            {t("methodComparison")}
          </button>
        </div>

        {activeTab === "download" && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground font-mono">{t("reportsUseSelected")}</p>
            <div className="grid md:grid-cols-2 gap-4">
              {reportTypes.map(({ key, titleKey, descKey }) => (
                <div key={key} className="card-glass">
                  {/* Icon placeholder */}
                  <div className="w-10 h-10 rounded-lg border border-border/50 mb-4 flex items-center justify-center">
                    <span className="font-mono text-xs text-muted-foreground uppercase">
                      {key === "json" ? "{}" : key === "form8949" ? "SO" : key === "turbotax" ? "CSV" : "D"}
                    </span>
                  </div>
                  <h3 className="font-mono text-base font-semibold mb-1">{t(titleKey)}</h3>
                  <p className="text-sm text-muted-foreground mb-4">{t(descKey)}</p>
                  <button
                    onClick={() => handleDownload(key === "schedule_d" ? "schedule-d" : key)}
                    className="btn-accent inline-block text-center"
                    disabled={!engine.result}
                  >
                    {t("downloadYearMethod", { year, method })}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "compare" && (
          <div>
            {comparison ? (
              <div className="glass rounded-lg overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{tc("method")}</th>
                      <th className="text-right px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("totalGains")}</th>
                      <th className="text-right px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("totalLosses")}</th>
                      <th className="text-right px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("net")}</th>
                      <th className="text-right px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("txns")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(["FIFO", "LIFO", "HIFO"] as const).map((m) => {
                      const d = comparison[m];
                      return (
                        <tr
                          key={m}
                          className={`border-b border-border/50 ${m === method ? "bg-primary/5 border-l-2 border-l-primary" : "hover:bg-white/5"} transition-colors`}
                        >
                          <td className="px-4 py-3 font-mono font-semibold">{m}</td>
                          {d ? (
                            <>
                              <td className="px-4 py-3 text-right font-data text-green-400">{fmt(d.totalGains)}</td>
                              <td className="px-4 py-3 text-right font-data text-red-400">{fmt(d.totalLosses)}</td>
                              <td className={`px-4 py-3 text-right font-data font-semibold ${netColor(d.net)}`}>{fmt(d.net)}</td>
                              <td className="px-4 py-3 text-right font-mono text-muted-foreground">{"\u2014"}</td>
                            </>
                          ) : (
                            <td colSpan={4} className="px-4 py-3 text-muted-foreground font-mono text-sm">
                              {t("notCalculated")}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted-foreground font-mono text-sm">{t("runFirst")}</p>
            )}
          </div>
        )}
      </div>

      {/* Method info */}
      <div className="glass rounded-lg p-4 animate-fade-in-up delay-3">
        <p className="font-mono text-xs text-muted-foreground">
          {t("reportsUseSelected")}
        </p>
      </div>
    </div>
  );
}
