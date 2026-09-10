"use client";

import { ReactNode, useMemo } from "react";

// --- EVM (wagmi + viem) ---
import { WagmiProvider, createConfig, http } from "wagmi";
import { mainnet, polygon, arbitrum, base, optimism } from "wagmi/chains";
import { injected } from "wagmi/connectors";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// --- Solana ---
import {
  ConnectionProvider,
  WalletProvider as SolanaWalletProvider,
} from "@solana/wallet-adapter-react";
import { PhantomWalletAdapter } from "@solana/wallet-adapter-wallets";
import "@solana/wallet-adapter-react-ui/styles.css";

// EVM config: MetaMask via injected connector
const wagmiConfig = createConfig({
  chains: [mainnet, polygon, arbitrum, base, optimism],
  connectors: [injected()],
  transports: {
    [mainnet.id]: http(),
    [polygon.id]: http(),
    [arbitrum.id]: http(),
    [base.id]: http(),
    [optimism.id]: http(),
  },
});

const queryClient = new QueryClient();

// Solana RPC endpoint (mainnet-beta public)
const SOLANA_RPC =
  process.env.NEXT_PUBLIC_SOLANA_RPC ?? "https://api.mainnet-beta.solana.com";

export function WalletProviders({ children }: { children: ReactNode }) {
  const solanaWallets = useMemo(() => [new PhantomWalletAdapter()], []);

  return (
    <QueryClientProvider client={queryClient}>
      <WagmiProvider config={wagmiConfig}>
        <ConnectionProvider endpoint={SOLANA_RPC}>
          <SolanaWalletProvider wallets={solanaWallets} autoConnect>
            {children}
          </SolanaWalletProvider>
        </ConnectionProvider>
      </WagmiProvider>
    </QueryClientProvider>
  );
}
