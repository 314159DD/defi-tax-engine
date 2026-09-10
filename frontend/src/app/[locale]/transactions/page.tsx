"use client";

import { useEffect, useState, use } from "react";
import { useTranslations } from "next-intl";
import type { Transaction, TransactionPage } from "@/lib/api";
import { localTransactions } from "@/lib/local-api";

const TX_TYPES = [
  "transfer", "swap", "lp_add", "lp_remove", "stake", "unstake",
  "reward", "bridge", "airdrop", "mint", "burn", "approve", "unknown",
];

const CHAINS = ["ethereum", "polygon", "arbitrum", "base", "optimism", "solana"];

function TxTypeDot({ type }: { type: string }) {
  const dotColors: Record<string, string> = {
    swap: "bg-blue-400",
    lp_add: "bg-purple-400",
    lp_remove: "bg-purple-300",
    stake: "bg-green-400",
    unstake: "bg-green-300",
    reward: "bg-yellow-400",
    bridge: "bg-slate-400",
    airdrop: "bg-pink-400",
    transfer: "bg-gray-400",
  };
  return (
    <span className="flex items-center gap-2">
      <span className={`w-2 h-2 rounded-full ${dotColors[type] ?? "bg-gray-400"}`} />
      <span className="font-mono text-xs">{type}</span>
    </span>
  );
}

export default function TransactionsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const params = use(searchParams);
  const pageFromUrl = Number(params.page ?? 1);

  const t = useTranslations("transactions");
  const tc = useTranslations("common");

  const [data, setData] = useState<TransactionPage | null>(null);
  const [page, setPage] = useState(pageFromUrl);
  const [filterChain, setFilterChain] = useState<string>("");
  const [filterType, setFilterType] = useState<string>("");
  const [filterYear, setFilterYear] = useState<string>("");
  const [filterMissingPrice, setFilterMissingPrice] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Override modal
  const [overrideTx, setOverrideTx] = useState<Transaction | null>(null);
  const [overrideType, setOverrideType] = useState("");
  const [overriding, setOverriding] = useState(false);

  useEffect(() => {
    setLoading(true);
    localTransactions
      .list({
        page,
        page_size: 50,
        ...(filterChain ? { chain: filterChain } : {}),
        ...(filterType ? { tx_type: filterType } : {}),
        ...(filterYear ? { year: Number(filterYear) } : {}),
        ...(filterMissingPrice ? { missing_price: true } : {}),
      })
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [page, filterChain, filterType, filterYear, filterMissingPrice]);

  const handleOverride = async () => {
    if (!overrideTx || !overrideType) return;
    setOverriding(true);
    try {
      await localTransactions.overrideCategory(overrideTx.tx_hash, overrideTx.chain, overrideType);
      setOverrideTx(null);
      setData((prev) =>
        prev
          ? {
              ...prev,
              transactions: prev.transactions.map((t) =>
                t.tx_hash === overrideTx.tx_hash ? { ...t, tx_type: overrideType } : t
              ),
            }
          : prev
      );
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setOverriding(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-12 md:py-20 space-y-8">
      {/* Header */}
      <div className="flex items-center gap-4 animate-fade-in-up">
        <h1 className="font-display text-3xl md:text-4xl font-bold">{t("title")}</h1>
        {data && (
          <span className="glass rounded-md px-3 py-1 font-mono text-sm text-muted-foreground">
            {data.total.toLocaleString()}
          </span>
        )}
      </div>

      {/* Filter bar */}
      <div className="glass rounded-lg p-4 flex flex-wrap gap-3 items-center animate-fade-in-up delay-1">
        {/* Chain filter */}
        <select
          value={filterChain}
          onChange={(e) => { setFilterChain(e.target.value); setPage(1); }}
          className="bg-transparent border border-border rounded-md px-3 py-2 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
        >
          <option value="">{tc("allChains")}</option>
          {CHAINS.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        {/* Type filter */}
        <select
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value); setPage(1); }}
          className="bg-transparent border border-border rounded-md px-3 py-2 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
        >
          <option value="">{tc("allTypes")}</option>
          {TX_TYPES.map((tp) => (
            <option key={tp} value={tp}>{tp}</option>
          ))}
        </select>

        {/* Year search */}
        <input
          className="bg-transparent border border-border rounded-md px-3 py-2 w-24 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
          placeholder={tc("year")}
          value={filterYear}
          onChange={(e) => { setFilterYear(e.target.value); setPage(1); }}
        />

        {/* Missing price toggle */}
        <label className="flex items-center gap-2 font-mono text-sm text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={filterMissingPrice}
            onChange={(e) => { setFilterMissingPrice(e.target.checked); setPage(1); }}
            className="accent-primary"
          />
          {t("missingPrice")}
        </label>
      </div>

      {error && <div className="text-red-400 font-mono text-sm">{error}</div>}

      {/* Table */}
      <div className="glass rounded-lg overflow-hidden animate-fade-in-up delay-2">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("timestamp")}</th>
                <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{tc("chain")}</th>
                <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("type")}</th>
                <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("protocol")}</th>
                <th className="text-left px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("hash")}</th>
                <th className="text-right px-4 py-3 font-mono text-xs uppercase tracking-wider text-muted-foreground">{t("override")}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center text-muted-foreground py-16 font-mono">
                    {tc("loading")}
                  </td>
                </tr>
              ) : data?.transactions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center text-muted-foreground py-16 font-mono">
                    {t("noTransactions")}
                  </td>
                </tr>
              ) : (
                data?.transactions.map((tx) => (
                  <tr
                    key={`${tx.chain}-${tx.tx_hash}`}
                    className="border-b border-border/50 hover:bg-white/5 transition-colors group hover:border-l-2 hover:border-l-primary"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground whitespace-nowrap">
                      {tx.timestamp ? new Date(tx.timestamp).toLocaleString() : "\u2014"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="glass rounded-md px-2.5 py-0.5 font-mono text-xs capitalize">
                        {tx.chain}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <TxTypeDot type={tx.tx_type ?? "unknown"} />
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{tx.protocol ?? "\u2014"}</td>
                    <td className="px-4 py-3 font-mono text-xs max-w-[140px] truncate text-muted-foreground">
                      {tx.tx_hash}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => { setOverrideTx(tx); setOverrideType(tx.tx_type ?? ""); }}
                        className="btn-ghost px-3 py-1.5 text-xs"
                      >
                        {tc("edit")}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between animate-fade-in-up delay-3">
          <button
            className="btn-ghost px-4 py-2 text-sm disabled:opacity-30"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            {tc("previous")}
          </button>
          <span className="font-mono text-sm text-muted-foreground">
            {tc("page", { current: page, total: data.pages })}
          </span>
          <button
            className="btn-ghost px-4 py-2 text-sm disabled:opacity-30"
            disabled={page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            {tc("next")}
          </button>
        </div>
      )}

      {/* Override category modal */}
      {overrideTx && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOverrideTx(null)} />
          <div className="relative card-glass-accent max-w-md w-full mx-4 p-6 space-y-4">
            <h2 className="font-display text-lg font-bold">{t("overrideTitle")}</h2>
            <p className="font-mono text-sm text-muted-foreground break-all">{overrideTx.tx_hash}</p>
            <select
              value={overrideType}
              onChange={(e) => setOverrideType(e.target.value)}
              className="w-full bg-transparent border border-border rounded-md px-3 py-2 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value="" disabled>{t("selectType")}</option>
              {TX_TYPES.map((tp) => (
                <option key={tp} value={tp}>{tp}</option>
              ))}
            </select>
            <div className="flex gap-3 justify-end pt-2">
              <button className="btn-ghost" onClick={() => setOverrideTx(null)}>{tc("cancel")}</button>
              <button className="btn-primary" onClick={handleOverride} disabled={overriding || !overrideType}>
                {overriding ? tc("loading") : tc("save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
