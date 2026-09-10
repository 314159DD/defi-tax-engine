"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { useAuth } from "@/hooks/useAuth";
import { isSupabaseConfigured } from "@/lib/supabase";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const locale = useLocale();

  useEffect(() => {
    if (!isSupabaseConfigured) return; // dev mode: skip auth
    if (!loading && !user) {
      router.replace(`/${locale}/login`);
    }
  }, [user, loading, router, locale]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <span className="font-mono text-sm text-muted-foreground animate-pulse">
          Loading…
        </span>
      </div>
    );
  }

  if (!isSupabaseConfigured) return <>{children}</>; // dev mode
  if (!user) return null;

  return <>{children}</>;
}
