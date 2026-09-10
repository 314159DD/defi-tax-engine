"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const t = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const { signIn } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const { error: err } = await signIn(email, password);
    if (err) {
      setError(err);
      setLoading(false);
    } else {
      router.push(`/${locale}/dashboard`);
    }
  };

  return (
    <div className="w-full max-w-sm space-y-6 animate-fade-in-up">
      <div className="text-center">
        <Link href="/" className="inline-flex items-center gap-0 mb-6">
          <span className="font-mono text-xl font-bold tracking-tight text-foreground">
            CRYPTO
          </span>
          <span className="font-mono text-xl font-bold tracking-tight text-primary">
            TAX
          </span>
        </Link>
        <h1 className="font-display text-2xl font-semibold">{t("loginTitle")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("loginSubtitle")}</p>
      </div>

      <form onSubmit={handleSubmit} className="card-glass-accent space-y-4">
        <div>
          <label
            htmlFor="email"
            className="font-mono text-xs text-muted-foreground uppercase tracking-wider block mb-1.5"
          >
            {t("email")}
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("emailPlaceholder")}
            className="w-full bg-transparent border border-border rounded-md px-4 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
          />
        </div>

        <div>
          <label
            htmlFor="password"
            className="font-mono text-xs text-muted-foreground uppercase tracking-wider block mb-1.5"
          >
            {t("password")}
          </label>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className="w-full bg-transparent border border-border rounded-md px-4 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
          />
        </div>

        {error && <p className="text-red-400 font-mono text-sm">{error}</p>}

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? t("signingIn") : t("signIn")}
        </button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        {t("noAccount")}{" "}
        <Link href="/signup" className="text-primary hover:underline font-medium">
          {t("signUpLink")}
        </Link>
      </p>
    </div>
  );
}
