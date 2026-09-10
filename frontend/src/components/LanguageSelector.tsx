"use client";

import { useLocale } from "next-intl";
import { useRouter, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

export function LanguageSelector() {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  function switchTo(newLocale: string) {
    if (newLocale !== locale) {
      router.replace(pathname, { locale: newLocale });
    }
  }

  return (
    <div className="flex items-center gap-1 font-mono text-sm">
      <button
        onClick={() => switchTo("en")}
        className={cn(
          "px-1.5 py-0.5 rounded transition-colors duration-200",
          locale === "en"
            ? "text-primary font-semibold"
            : "text-muted-foreground hover:text-foreground"
        )}
      >
        EN
      </button>
      <span className="text-muted-foreground/40">|</span>
      <button
        onClick={() => switchTo("de")}
        className={cn(
          "px-1.5 py-0.5 rounded transition-colors duration-200",
          locale === "de"
            ? "text-primary font-semibold"
            : "text-muted-foreground hover:text-foreground"
        )}
      >
        DE
      </button>
    </div>
  );
}
