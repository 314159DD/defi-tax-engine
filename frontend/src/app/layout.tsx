import type { Metadata } from "next";
import "./globals.css";

// All pages are client-rendered (SPA); disable static prerendering
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Crypto Tax DeFi - Accurate DeFi Tax Reporting",
  description:
    "Multi-chain crypto tax calculator with DeFi-aware categorization. FIFO, LIFO, HIFO cost basis. IRS Form 8949, Schedule D, and TurboTax export.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
