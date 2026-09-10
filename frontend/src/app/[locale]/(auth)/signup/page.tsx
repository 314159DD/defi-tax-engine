"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuth } from "@/hooks/useAuth";

export default function SignupPage() {
  const t = useTranslations("auth");
  const { signUp } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError(t("passwordMismatch"));
      return;
    }
    if (password.length < 8) {
      setError(t("passwordTooShort"));
      return;
    }
    setLoading(true);
    setError(null);
    const { error: err } = await signUp(email, password);
    if (err) {
      setError(err);
      setLoading(false);
    } else {
      setSuccess(true);
      setLoading(false);
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
        <h1 className="font-display text-2xl font-semibold">{t("signupTitle")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("signupSubtitle")}</p>
      </div>

      {success ? (
        <div className="card-glass-accent text-center space-y-3">
          <p className="font-mono text-sm text-primary">{t("checkEmail")}</p>
          <p className="text-sm text-muted-foreground">{t("checkEmailDesc")}</p>
          <Link href="/login" className="btn-primary inline-block mt-2">
            {t("backToLogin")}
          </Link>
        </div>
      ) : (
        <>
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
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-transparent border border-border rounded-md px-4 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
              />
            </div>

            <div>
              <label
                htmlFor="confirm"
                className="font-mono text-xs text-muted-foreground uppercase tracking-wider block mb-1.5"
              >
                {t("confirmPassword")}
              </label>
              <input
                id="confirm"
                type="password"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-transparent border border-border rounded-md px-4 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50"
              />
            </div>

            {error && <p className="text-red-400 font-mono text-sm">{error}</p>}

            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? t("creatingAccount") : t("createAccount")}
            </button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            {t("hasAccount")}{" "}
            <Link
              href="/login"
              className="text-primary hover:underline font-medium"
            >
              {t("signInLink")}
            </Link>
          </p>
        </>
      )}
    </div>
  );
}
