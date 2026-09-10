"use client";

import { useState, useCallback } from "react";
import { useConnect, useAccount, useDisconnect } from "wagmi";
import { useWallet } from "@solana/wallet-adapter-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { localWallets as walletsApi, localImport as importApi } from "@/lib/local-api";

// Map wagmi chain IDs to our backend chain names
const CHAIN_ID_MAP: Record<number, string> = {
  1: "ethereum",
  137: "polygon",
  42161: "arbitrum",
  8453: "base",
  10: "optimism",
};

interface WalletConnectButtonProps {
  /** Called after a wallet is successfully registered (so parent can refresh) */
  onWalletRegistered?: () => void;
}

export function WalletConnectButton({ onWalletRegistered }: WalletConnectButtonProps) {
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // --- EVM (MetaMask) ---
  const { connect, connectors } = useConnect();
  const { address: evmAddress, chainId, isConnected: evmConnected } = useAccount();
  const { disconnect: evmDisconnect } = useDisconnect();

  // --- Solana (Phantom) ---
  const {
    publicKey: solanaPublicKey,
    connected: solanaConnected,
    select: selectSolanaWallet,
    connect: connectSolana,
    disconnect: solanaDisconnect,
    wallets: solanaWallets,
  } = useWallet();

  const registerAndImport = useCallback(
    async (address: string, chain: string) => {
      setRegistering(true);
      setError(null);
      setSuccess(null);
      try {
        await walletsApi.add({ address, chain, label: `Connected (${chain})` });
        // Trigger auto-import
        await importApi.trigger(address, chain);
        setSuccess(`${chain} wallet connected and import started`);
        onWalletRegistered?.();
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        // If wallet already exists, that's okay
        if (msg.includes("already exists") || msg.includes("UNIQUE")) {
          setSuccess(`${chain} wallet already registered - triggering re-import`);
          try {
            await importApi.trigger(address, chain);
          } catch {
            // ignore re-import errors
          }
          onWalletRegistered?.();
        } else {
          setError(msg);
        }
      } finally {
        setRegistering(false);
      }
    },
    [onWalletRegistered],
  );

  const handleMetaMask = useCallback(async () => {
    setError(null);
    setSuccess(null);

    if (evmConnected && evmAddress && chainId) {
      // Already connected - register it
      const chain = CHAIN_ID_MAP[chainId] ?? "ethereum";
      await registerAndImport(evmAddress, chain);
      return;
    }

    // Find MetaMask / injected connector
    const injectedConnector = connectors.find(
      (c) => c.id === "injected" || c.name.toLowerCase().includes("metamask"),
    );
    if (!injectedConnector) {
      setError("MetaMask not detected. Please install the MetaMask extension.");
      return;
    }

    connect(
      { connector: injectedConnector },
      {
        onSuccess: async (data) => {
          const addr = data.accounts[0];
          const cId = data.chainId;
          if (addr) {
            const chain = CHAIN_ID_MAP[cId] ?? "ethereum";
            await registerAndImport(addr, chain);
          }
        },
        onError: (err) => {
          setError(err.message);
        },
      },
    );
  }, [evmConnected, evmAddress, chainId, connectors, connect, registerAndImport]);

  const handlePhantom = useCallback(async () => {
    setError(null);
    setSuccess(null);

    if (solanaConnected && solanaPublicKey) {
      await registerAndImport(solanaPublicKey.toBase58(), "solana");
      return;
    }

    // Select Phantom adapter and connect
    const phantomAdapter = solanaWallets.find(
      (w) => w.adapter.name.toLowerCase() === "phantom",
    );
    if (!phantomAdapter) {
      setError("Phantom wallet not detected. Please install the Phantom extension.");
      return;
    }

    try {
      selectSolanaWallet(phantomAdapter.adapter.name);
      await connectSolana();
      // After connect, publicKey should be available on next render.
      // We register in a timeout to allow state to settle.
      setTimeout(async () => {
        if (solanaPublicKey) {
          await registerAndImport(solanaPublicKey.toBase58(), "solana");
        }
      }, 500);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [
    solanaConnected,
    solanaPublicKey,
    solanaWallets,
    selectSolanaWallet,
    connectSolana,
    registerAndImport,
  ]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        {/* MetaMask */}
        <Button
          variant="outline"
          disabled={registering}
          onClick={handleMetaMask}
          className="gap-2"
        >
          <span className="text-lg">🦊</span>
          {evmConnected ? "Register MetaMask Wallet" : "Connect MetaMask"}
        </Button>

        {/* Phantom */}
        <Button
          variant="outline"
          disabled={registering}
          onClick={handlePhantom}
          className="gap-2"
        >
          <span className="text-lg">👻</span>
          {solanaConnected ? "Register Phantom Wallet" : "Connect Phantom"}
        </Button>
      </div>

      {/* Connected wallet indicators */}
      <div className="flex flex-wrap gap-2">
        {evmConnected && evmAddress && (
          <Badge variant="secondary" className="gap-1 font-mono text-xs">
            EVM: {evmAddress.slice(0, 6)}...{evmAddress.slice(-4)}
            <button
              onClick={() => evmDisconnect()}
              className="ml-1 text-muted-foreground hover:text-foreground"
              title="Disconnect"
            >
              ✕
            </button>
          </Badge>
        )}
        {solanaConnected && solanaPublicKey && (
          <Badge variant="secondary" className="gap-1 font-mono text-xs">
            SOL: {solanaPublicKey.toBase58().slice(0, 6)}...
            {solanaPublicKey.toBase58().slice(-4)}
            <button
              onClick={() => solanaDisconnect()}
              className="ml-1 text-muted-foreground hover:text-foreground"
              title="Disconnect"
            >
              ✕
            </button>
          </Badge>
        )}
      </div>

      {registering && (
        <p className="text-sm text-yellow-400">Registering wallet and starting import...</p>
      )}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {success && <p className="text-sm text-green-400">{success}</p>}
    </div>
  );
}
