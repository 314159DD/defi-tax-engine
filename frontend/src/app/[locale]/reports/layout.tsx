"use client";

import { RequireAuth } from "@/components/RequireAuth";

export default function ReportsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <RequireAuth>{children}</RequireAuth>;
}
