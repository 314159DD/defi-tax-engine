"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface EstimateResult {
  address: string;
  chain: string;
  year: number;
  imported: boolean;
  total_gains: string;
  total_losses: string;
  net_gain_loss: string;
  transaction_count: number;
  teaser_message: string;
  cta: string;
}

const SUPPORTED_CHAINS = [
  { value: "ethereum", label: "Ethereum" },
  { value: "arbitrum", label: "Arbitrum" },
  { value: "optimism", label: "Optimism" },
  { value: "polygon", label: "Polygon" },
  { value: "base", label: "Base" },
  { value: "solana", label: "Solana" },
];

function fmt(val: string): string {
  const n = parseFloat(val);
  if (isNaN(n) || n === 0) return "$0.00";
  const abs = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return n < 0 ? `-$${abs}` : `$${abs}`;
}

function netColor(val: string): string {
  const n = parseFloat(val);
  if (n > 0) return "text-red-400";
  if (n < 0) return "text-green-400";
  return "text-muted-foreground";
}

export default function EstimatePage() {
  const t = useTranslations("estimate");
  const tc = useTranslations("common");

  const [address, setAddress] = useState("");
  const [chain, setChain] = useState("ethereum");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<EstimateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!address.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${BASE_URL}/api/estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: address.trim(), chain }),
      });

      if (res.status === 429) {
        setError(t("rateLimited"));
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setError(err.detail ?? tc("error"));
        return;
      }
      const data: EstimateResult = await res.json();
      setResult(data);
    } catch {
      setError(t("connectionError"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-16 md:py-24 space-y-10">
      {/* Header */}
      <div className="text-center animate-fade-in-up">
        <h1 className="font-display text-3xl md:text-4xl font-bold mb-3">
          <span className="text-gradient-amber">{t("title")}</span>
        </h1>
        <p className="text-muted-foreground text-base">
          {t("subtitle")}{" "}
          <strong className="text-foreground">{t("noSignup")}</strong>
        </p>
      </div>

      {/* Input card */}
      <div className="card-glass-accent glow-amber animate-fade-in-up delay-1">
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Address input */}
          <div>
            <label htmlFor="estimate-address" className="font-mono text-xs text-muted-foreground uppercase tracking-wider block mb-1.5">
              {t("walletAddress")}
            </label>
            <input
              id="estimate-address"
              placeholder={t("addressPlaceholder")}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full bg-transparent border border-border rounded-md px-4 py-3 font-mono text-base text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
              required
            />
          </div>

          {/* Chain selector */}
          <div>
            <label htmlFor="estimate-chain" className="font-mono text-xs text-muted-foreground uppercase tracking-wider block mb-1.5">
              {t("chain")}
            </label>
            <select
              id="estimate-chain"
              value={chain}
              onChange={(e) => setChain(e.target.value)}
              className="w-full bg-transparent border border-border rounded-md px-3 py-2.5 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
            >
              {SUPPORTED_CHAINS.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          <button
            type="submit"
            className="btn-primary w-full py-3 text-base"
            disabled={loading || !address.trim()}
          >
            {loading ? t("calculating") : t("getEstimate")}
          </button>
        </form>
      </div>

      {/* Error */}
      {error && (
        <div className="glass rounded-lg border border-red-500/30 p-4 text-red-400 font-mono text-sm animate-fade-in-up">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4 animate-fade-in-up">
          <div className="card-glass">
            <div className="flex items-center gap-2 mb-4">
              <h2 className="font-mono text-sm font-semibold">
                {t("taxYear", {
                  year: result.year,
                  chain: result.chain.charAt(0).toUpperCase() + result.chain.slice(1),
                })}
              </h2>
            </div>
            <p className="font-mono text-xs text-muted-foreground mb-4">
              {result.address.slice(0, 10)}\u2026{result.address.slice(-6)}
            </p>

            {!result.imported ? (
              <p className="text-sm text-muted-foreground">{t("notImported")}</p>
            ) : (
              <div className="grid grid-cols-3 gap-6 mb-6">
                <div className="text-center">
                  <div className="font-mono text-xs text-muted-foreground mb-1">{t("gains")}</div>
                  <div className="font-data text-xl font-bold text-green-400">{fmt(result.total_gains)}</div>
                </div>
                <div className="text-center">
                  <div className="font-mono text-xs text-muted-foreground mb-1">{t("losses")}</div>
                  <div className="font-data text-xl font-bold text-red-400">{fmt(result.total_losses)}</div>
                </div>
                <div className="text-center">
                  <div className="font-mono text-xs text-muted-foreground mb-1">{t("net")}</div>
                  <div className={`font-data text-3xl font-bold ${netColor(result.net_gain_loss)}`}>
                    {fmt(result.net_gain_loss)}
                  </div>
                </div>
              </div>
            )}

            <div className="glass rounded-md p-4 space-y-3">
              <p className="text-sm text-foreground">{result.teaser_message}</p>
              <Link href="/pricing" className="btn-primary block text-center w-full">
                {result.cta}
              </Link>
            </div>
          </div>

          <p className="text-xs font-mono text-muted-foreground text-center">
            {t("disclaimer")}
          </p>
        </div>
      )}

      {/* Feature teaser (shown when no results) */}
      {!result && !loading && (
        <div className="card-glass animate-fade-in-up delay-2">
          <h3 className="font-mono text-sm font-semibold mb-3">{t("freeAccountTitle")}</h3>
          <ul className="space-y-2 text-sm text-muted-foreground mb-4">
            {[1, 2, 3, 4, 5].map((n) => (
              <li key={n} className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                {t(`freeFeature${n}` as "freeFeature1")}
              </li>
            ))}
          </ul>
          <Link href="/pricing" className="btn-ghost inline-block">
            {t("viewPricing")}
          </Link>
        </div>
      )}
    </div>
  );
}
