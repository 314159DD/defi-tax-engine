"use client";

import { useState, useEffect, useCallback } from "react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { LanguageSelector } from "@/components/LanguageSelector";
import { useAuth } from "@/hooks/useAuth";

const NAV_LINKS = [
  { href: "/dashboard", key: "dashboard" },
  { href: "/pricing", key: "pricing" },
  { href: "/blog", key: "blog" },
] as const;

export function NavBar() {
  const t = useTranslations("nav");
  const ta = useTranslations("auth");
  const pathname = usePathname() ?? "";
  const { user, loading: authLoading, signOut } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleScroll = useCallback(() => {
    setScrolled(window.scrollY > 20);
  }, []);

  useEffect(() => {
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Prevent body scroll when mobile menu open
  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  return (
    <>
      <nav
        className={cn(
          "fixed top-0 left-0 right-0 z-50 transition-all duration-300",
          scrolled
            ? "glass shadow-lg shadow-black/20"
            : "bg-transparent"
        )}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-0 shrink-0">
              <span className="font-mono text-lg font-bold tracking-tight text-foreground">
                CRYPTO
              </span>
              <span className="font-mono text-lg font-bold tracking-tight text-primary">
                TAX
              </span>
            </Link>

            {/* Center nav links - hidden on mobile */}
            <div className="hidden md:flex items-center gap-1">
              {NAV_LINKS.map(({ href, key }) => (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "px-4 py-2 rounded-md text-sm font-medium transition-colors duration-200",
                    pathname.startsWith(href)
                      ? "text-primary bg-primary/10"
                      : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                  )}
                >
                  {t(key)}
                </Link>
              ))}
            </div>

            {/* Right side */}
            <div className="hidden md:flex items-center gap-4">
              <LanguageSelector />
              {authLoading ? null : user ? (
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-muted-foreground truncate max-w-[140px]">
                    {user.email}
                  </span>
                  <button
                    onClick={() => signOut()}
                    className="btn-ghost px-3 py-1.5 text-xs"
                  >
                    {ta("signOut")}
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <Link
                    href="/login"
                    className="btn-ghost px-3 py-1.5 text-sm"
                  >
                    {ta("signIn")}
                  </Link>
                  <Link href="/signup" className="btn-primary">
                    {t("getStarted")}
                  </Link>
                </div>
              )}
            </div>

            {/* Mobile hamburger */}
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden flex flex-col justify-center items-center w-10 h-10 gap-1.5"
              aria-label={mobileOpen ? t("close") : t("menu")}
            >
              <span
                className={cn(
                  "block w-5 h-0.5 bg-foreground transition-all duration-300 origin-center",
                  mobileOpen && "rotate-45 translate-y-[4px]"
                )}
              />
              <span
                className={cn(
                  "block w-5 h-0.5 bg-foreground transition-all duration-300",
                  mobileOpen && "opacity-0"
                )}
              />
              <span
                className={cn(
                  "block w-5 h-0.5 bg-foreground transition-all duration-300 origin-center",
                  mobileOpen && "-rotate-45 -translate-y-[4px]"
                )}
              />
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile overlay */}
      <div
        className={cn(
          "fixed inset-0 z-40 transition-all duration-300 md:hidden",
          mobileOpen
            ? "opacity-100 pointer-events-auto"
            : "opacity-0 pointer-events-none"
        )}
      >
        <div className="absolute inset-0 bg-background/95 backdrop-blur-xl" />
        <div className="relative flex flex-col items-center justify-center h-full gap-8">
          {NAV_LINKS.map(({ href, key }, i) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "text-3xl font-mono font-semibold transition-all duration-300",
                pathname.startsWith(href)
                  ? "text-primary"
                  : "text-foreground hover:text-primary",
                mobileOpen
                  ? "opacity-100 translate-y-0"
                  : "opacity-0 translate-y-4",
              )}
              style={{
                transitionDelay: mobileOpen ? `${(i + 1) * 75}ms` : "0ms",
              }}
            >
              {t(key)}
            </Link>
          ))}

          <div
            className={cn(
              "flex flex-col items-center gap-6 mt-4 transition-all duration-300",
              mobileOpen
                ? "opacity-100 translate-y-0"
                : "opacity-0 translate-y-4"
            )}
            style={{
              transitionDelay: mobileOpen
                ? `${(NAV_LINKS.length + 1) * 75}ms`
                : "0ms",
            }}
          >
            <LanguageSelector />
            {authLoading ? null : user ? (
              <button
                onClick={() => signOut()}
                className="btn-ghost text-lg px-8 py-3"
              >
                {ta("signOut")}
              </button>
            ) : (
              <div className="flex flex-col items-center gap-3">
                <Link href="/login" className="btn-ghost text-lg px-8 py-3">
                  {ta("signIn")}
                </Link>
                <Link href="/signup" className="btn-primary text-lg px-8 py-3">
                  {t("getStarted")}
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Spacer so content doesn't hide behind fixed nav */}
      <div className="h-16" />
    </>
  );
}
