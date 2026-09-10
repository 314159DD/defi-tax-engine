"use client";

import { WalletProviders } from "@/components/WalletProviders";
import { RequireAuth } from "@/components/RequireAuth";

export default function WalletsLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <WalletProviders>{children}</WalletProviders>
    </RequireAuth>
  );
}
