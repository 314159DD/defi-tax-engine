"use client";

import { RequireAuth } from "@/components/RequireAuth";

export default function TransactionsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <RequireAuth>{children}</RequireAuth>;
}
