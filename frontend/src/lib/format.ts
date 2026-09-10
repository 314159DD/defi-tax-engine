/**
 * Locale-aware formatting utilities for currency, dates, and numbers.
 *
 * US: $1,234.56  |  DE: 1.234,56 €
 * US: 03/26/2026 |  DE: 26.03.2026
 */

const LOCALE_MAP: Record<string, string> = {
  en: "en-US",
  de: "de-DE",
};

function resolveLocale(locale: string): string {
  return LOCALE_MAP[locale] ?? locale;
}

/**
 * Format a monetary amount with locale-appropriate currency symbol and separators.
 * US: $1,234.56  |  DE: 1.234,56 €
 */
export function formatCurrency(
  amount: number | string,
  locale: string,
  currency?: string,
): string {
  const n = typeof amount === "string" ? parseFloat(amount) : amount;
  if (isNaN(n)) return locale === "de" ? "0,00 €" : "$0.00";

  const resolvedLocale = resolveLocale(locale);
  const cur = currency ?? (locale === "de" ? "EUR" : "USD");

  return new Intl.NumberFormat(resolvedLocale, {
    style: "currency",
    currency: cur,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

/**
 * Format a date with locale-appropriate format.
 * US: 03/26/2026  |  DE: 26.03.2026
 */
export function formatDate(date: Date | string, locale: string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  if (isNaN(d.getTime())) return "-";

  const resolvedLocale = resolveLocale(locale);
  return new Intl.DateTimeFormat(resolvedLocale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

/**
 * Format a number with locale-appropriate decimal and thousands separators.
 * US: 1,234.56  |  DE: 1.234,56
 */
export function formatNumber(n: number, locale: string, decimals = 2): string {
  if (isNaN(n)) return "0";

  const resolvedLocale = resolveLocale(locale);
  return new Intl.NumberFormat(resolvedLocale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(n);
}
