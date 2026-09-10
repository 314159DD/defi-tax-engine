"use client";

import { useRef, useEffect } from "react";

const CHAINS = [
  { name: "Bitcoin", symbol: "BTC", color: "#F7931A" },
  { name: "Ethereum", symbol: "ETH", color: "#627EEA" },
  { name: "Solana", symbol: "SOL", color: "#9945FF" },
  { name: "Polygon", symbol: "MATIC", color: "#8247E5" },
  { name: "Arbitrum", symbol: "ARB", color: "#28A0F0" },
  { name: "Base", symbol: "BASE", color: "#0052FF" },
  { name: "Optimism", symbol: "OP", color: "#FF0420" },
  { name: "Avalanche", symbol: "AVAX", color: "#E84142" },
  { name: "BSC", symbol: "BNB", color: "#F3BA2F" },
  { name: "Fantom", symbol: "FTM", color: "#1969FF" },
  { name: "Cosmos", symbol: "ATOM", color: "#6F7390" },
  { name: "zkSync", symbol: "ZK", color: "#8B8DFC" },
  { name: "Linea", symbol: "ETH", color: "#121212" },
  { name: "Scroll", symbol: "ETH", color: "#FFEEDA" },
  { name: "Mantle", symbol: "MNT", color: "#000000" },
];

function ChainPill({ name, symbol, color }: { name: string; symbol: string; color: string }) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-2 shrink-0">
      <div
        className="w-2 h-2 rounded-full shrink-0"
        style={{ background: color }}
      />
      <span className="font-mono text-xs text-[var(--vault-text-secondary)] whitespace-nowrap">
        {name}
      </span>
      <span className="font-mono text-[10px] text-[var(--vault-text-tertiary)]">
        {symbol}
      </span>
    </div>
  );
}

export function InfiniteChainTicker() {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    let animationId: number;
    let offset = 0;

    function tick() {
      offset += 0.4;
      if (offset >= el!.scrollWidth / 2) offset = 0;
      el!.style.transform = `translateX(-${offset}px)`;
      animationId = requestAnimationFrame(tick);
    }

    animationId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animationId);
  }, []);

  return (
    <div className="relative overflow-hidden border-y border-white/[0.04] py-1 bg-[oklch(0.11_0.005_260)]">
      {/* Fade masks */}
      <div className="absolute left-0 top-0 bottom-0 w-24 bg-gradient-to-r from-[oklch(0.11_0.005_260)] to-transparent z-10" />
      <div className="absolute right-0 top-0 bottom-0 w-24 bg-gradient-to-l from-[oklch(0.11_0.005_260)] to-transparent z-10" />

      <div ref={scrollRef} className="flex will-change-transform">
        {/* Double the list for seamless loop */}
        {[...CHAINS, ...CHAINS].map((chain, i) => (
          <ChainPill key={`${chain.name}-${i}`} {...chain} />
        ))}
      </div>
    </div>
  );
}
