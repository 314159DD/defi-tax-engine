# Sprint 4.7: Internationalization Framework

**Priority:** MEDIUM-HIGH - prerequisite for German launch. Must be done before German landing page, German dashboard features, and German content.
**Depends on:** Nothing (can be parallelized with other 4.x sprints)
**Files:** `frontend/` (all pages and components), `src/web/app.py` (backend locale)

---

## Task 4.7.1: Frontend i18n Setup

**Install:** `next-intl` (best Next.js 15 i18n library)

**Configure:**
- Route structure: `/en/...` and `/de/...` (locale prefix)
- Default locale: `en` (no prefix for English - `/dashboard` = English)
- German: `/de/dashboard`, `/de/wallets`, etc.
- Middleware: detect browser `Accept-Language`, redirect to preferred locale
- Manual override: language selector in nav (persisted in cookie)

**Create:**
- `frontend/messages/en.json` - all English strings
- `frontend/messages/de.json` - all German strings
- `frontend/src/i18n.ts` - configuration
- `frontend/src/middleware.ts` - locale detection + redirect

---

## Task 4.7.2: Extract All Hardcoded Strings

Go through every page and component, replace hardcoded English text with translation keys:

- Navigation: Dashboard, Wallets, Transactions, Reports, Pricing, Settings
- Dashboard: Tax Summary, Total Gains, Total Losses, Effective Rate, etc.
- Forms: labels, placeholders, validation messages, button text
- Reports: report names, download labels
- Pricing: tier names, feature descriptions, CTA text
- Errors: all error messages
- Tooltips and help text

**German translations must use correct Steuerrecht vocabulary:**
- "Capital gain" → "Veräußerungsgewinn" (not "Kapitalgewinn")
- "Holding period" → "Haltedauer" / "Spekulationsfrist"
- "Tax-free" → "steuerfrei"
- "Report" → "Steuerreport"
- "Cost basis" → "Anschaffungskosten"
- "Disposal" → "Veräußerung"
- "Income" → "Sonstige Einkünfte" (for staking/airdrops)

---

## Task 4.7.3: Number & Date Formatting

- German: `1.234,56 €` (dot thousands, comma decimal, € after)
- US: `$1,234.56` (comma thousands, dot decimal, $ before)
- German dates: `26.03.2026` (DD.MM.YYYY)
- US dates: `03/26/2026` (MM/DD/YYYY)

Use `Intl.NumberFormat` and `Intl.DateTimeFormat` with locale parameter.

---

## Task 4.7.4: Backend Locale Support

**Modify:** `src/web/app.py`

- Accept `Accept-Language` header or `?locale=de` parameter
- Report generation in user's locale:
  - US reports: English headers, USD amounts, MM/DD/YYYY dates
  - DE reports: German headers, EUR amounts, DD.MM.YYYY dates
- API error messages: localized based on user's locale setting
- Tax citations: English for US module, German for DE module
