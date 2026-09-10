"use client";

import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import type { Wallet, ImportStatus } from "@/lib/api";
import { localWallets, localImport } from "@/lib/local-api";
import { WalletConnectButton } from "@/components/WalletConnectButton";

const CHAINS = ["ethereum", "polygon", "arbitrum", "base", "optimism", "solana"];

export default function WalletsPage() {
  const t = useTranslations("wallets");

  const [walletList, setWalletList] = useState<Wallet[]>([]);
  const [address, setAddress] = useState("");
  const [chain, setChain] = useState("ethereum");
  const [label, setLabel] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importStatuses, setImportStatuses] = useState<Record<string, ImportStatus>>({});

  const load = useCallback(async () => {
    try {
      setWalletList(await localWallets.list());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleAdd = async () => {
    if (!address.trim()) return;
    setAdding(true);
    setError(null);
    try {
      const savedAddress = address.trim();
      const savedChain = chain;
      await localWallets.add({ address: savedAddress, chain: savedChain, label: label || undefined });
      setAddress("");
      setLabel("");
      await load();
      // Auto-import after adding
      const wallets = await localWallets.list();
      const added = wallets.find(
        (w) => w.address === savedAddress.toLowerCase() && w.chain === savedChain.toLowerCase(),
      );
      if (added) handleImport(added);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: string) => {
    await localWallets.delete(id);
    await load();
  };

  const handleImport = async (w: Wallet) => {
    const key = `${w.chain}:${w.address}`;
    setImportStatuses((prev) => ({ ...prev, [key]: { status: "running" } }));
    try {
      await localImport.trigger(w.address, w.chain);
      const poll = setInterval(async () => {
        const s = await localImport.status(w.address, w.chain);
        setImportStatuses((prev) => ({ ...prev, [key]: s }));
        if (s.status === "done" || s.status === "error") {
          clearInterval(poll);
          await load();
        }
      }, 2000);
    } catch (e: unknown) {
      setImportStatuses((prev) => ({
        ...prev,
        [key]: { status: "error", error: e instanceof Error ? e.message : String(e) },
      }));
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-12 md:py-20 space-y-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 animate-fade-in-up">
        <h1 className="font-display text-3xl md:text-4xl font-bold">{t("title")}</h1>
        <div className="sm:ml-auto">
          <WalletConnectButton onWalletRegistered={load} />
        </div>
      </div>

      {/* Add wallet section */}
      <div className="card-glass-accent animate-fade-in-up delay-1">
        <h2 className="font-mono text-lg font-semibold mb-4">{t("addManually")}</h2>
        <div className="space-y-4">
          {/* Address input */}
          <div>
            <label htmlFor="address" className="font-mono text-xs text-muted-foreground uppercase tracking-wider block mb-1.5">
              {t("walletAddress")}
            </label>
            <input
              id="address"
              placeholder={t("addressPlaceholder")}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full bg-transparent border border-border rounded-md px-4 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
            />
          </div>

          {/* Chain + label row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="font-mono text-xs text-muted-foreground uppercase tracking-wider block mb-1.5">
                {t("chain")}
              </label>
              <select
                value={chain}
                onChange={(e) => setChain(e.target.value)}
                className="w-full bg-transparent border border-border rounded-md px-3 py-2.5 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
              >
                {CHAINS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="label" className="font-mono text-xs text-muted-foreground uppercase tracking-wider block mb-1.5">
                {t("labelOptional")}
              </label>
              <input
                id="label"
                placeholder={t("labelPlaceholder")}
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                className="w-full bg-transparent border border-border rounded-md px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
              />
            </div>
          </div>

          {error && <p className="text-red-400 font-mono text-sm">{error}</p>}

          <button onClick={handleAdd} disabled={adding || !address.trim()} className="btn-primary">
            {adding ? t("adding") : t("addWallet")}
          </button>
        </div>
      </div>

      {/* Wallet list */}
      <div className="space-y-4 animate-fade-in-up delay-2">
        {walletList.length === 0 && (
          <p className="text-muted-foreground font-mono text-sm">{t("noWallets")}</p>
        )}
        {walletList.map((w) => {
          const key = `${w.chain}:${w.address}`;
          const status = importStatuses[key] ?? w.import_status;
          return (
            <div key={w.id} className="card-glass">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Chain badge + address */}
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="glass rounded-md px-2.5 py-0.5 font-mono text-xs capitalize">
                      {w.chain}
                    </span>
                    {w.label?.startsWith("Connected") ? (
                      <span className="glass rounded-md px-2.5 py-0.5 font-mono text-xs text-primary border border-primary/30">
                        {t("connected")}
                      </span>
                    ) : w.label ? (
                      <span className="font-mono text-xs text-muted-foreground">{w.label}</span>
                    ) : (
                      <span className="glass rounded-md px-2.5 py-0.5 font-mono text-xs text-muted-foreground">
                        {t("manual")}
                      </span>
                    )}
                  </div>

                  {/* Address */}
                  <p className="font-mono text-sm text-foreground truncate">
                    {w.address}
                  </p>

                  {/* Import status */}
                  {status?.status ? (
                    <p className="mt-1.5 font-mono text-xs text-muted-foreground">
                      {t("importStatus")}{" "}
                      <span
                        className={
                          status.status === "done"
                            ? "text-green-400"
                            : status.status === "error"
                            ? "text-red-400"
                            : "text-yellow-400"
                        }
                      >
                        {status.status === "running" ? "Importing..." : status.status}
                        {status.count !== undefined && status.count > 0 ? ` (${t("txnCount", { count: status.count })})` : ""}
                      </span>
                      {status.error && <span className="text-red-400"> - {status.error}</span>}
                    </p>
                  ) : !w.last_imported_at ? (
                    <p className="mt-1.5 font-mono text-xs text-yellow-400/80">
                      Not imported yet - click Import to fetch transactions
                    </p>
                  ) : null}

                  {/* Last imported */}
                  {w.last_imported_at && (
                    <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                      {t("lastImported", { date: new Date(w.last_imported_at).toLocaleString() })}
                    </p>
                  )}
                </div>

                {/* Actions */}
                <div className="flex gap-2 shrink-0">
                  <button
                    className={`px-4 py-2 text-xs font-mono font-semibold rounded-md transition-colors ${
                      status?.status === "running"
                        ? "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 cursor-wait"
                        : !w.last_imported_at
                        ? "bg-primary text-primary-foreground hover:bg-primary/90"
                        : "btn-ghost"
                    }`}
                    disabled={status?.status === "running"}
                    onClick={() => handleImport(w)}
                  >
                    {status?.status === "running" ? "Importing..." : !w.last_imported_at ? "Import Transactions" : t("import")}
                  </button>
                  <button
                    className="btn-ghost px-3 py-2 text-xs text-red-400 hover:text-red-300 hover:border-red-400/40"
                    onClick={() => handleDelete(w.id)}
                  >
                    {t("remove")}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
