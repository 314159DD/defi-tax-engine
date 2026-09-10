# Sprint 4.4: German Killer Features

**Priority:** HIGH - these features don't exist anywhere. They justify switching from CoinTracking/Blockpit.
**Depends on:** Sprint 4.2 (German tax module), Sprint 4.7 (i18n framework)
**Files:** `src/tax/de/`, new frontend dashboard components

---

## Task 4.4.1: Spekulationsfrist Dashboard

**Context:** German crypto held >12 months is completely tax-free. Users need to know EXACTLY when each lot becomes exempt. No competitor shows this as a real-time countdown.

**Create:** `frontend/src/app/dashboard/spekulationsfrist/` (new page/component)
**Modify:** `src/tax/de/module.py`, `src/calculator/lots.py`

**Backend:**
- Extend TaxLot with `spekulationsfrist_end: date` (acquisition_date + 365 days)
- Endpoint: `GET /api/tax/de/spekulationsfrist` → returns all lots with:
  - token, amount, acquisition_date, days_remaining, status (taxable/approaching/exempt)
  - current FMV, unrealized gain if sold now
  - tax_if_sold_now vs €0 if waited

**Frontend:**
- Per-lot countdown cards, grouped by token
- Color coding:
  - 🔴 Red: <90 days remaining (still fully taxable)
  - 🟡 Yellow: 90–270 days (approaching)
  - 🟢 Green: 270–365 days (almost there)
  - 🥇 Gold: >365 days (TAX FREE - Spekulationsfrist abgelaufen)
- Sort by: soonest to become exempt (default), largest value, token
- "Safe to sell" badge on exempt lots
- "Worth waiting" indicator: shows how much tax you'd save by waiting X more days

---

## Task 4.4.2: Freigrenze Real-Time Dashboard

**Context:** €1,000 Freigrenze is a CLIFF - €999 gains = €0 tax, €1,001 gains = full tax on €1,001. Users need to see exactly where they stand during the year, not just at year-end.

**Create:** `frontend/src/app/dashboard/freigrenze/` (new component)
**Modify:** `src/tax/de/module.py`

**Backend:**
- Endpoint: `GET /api/tax/de/freigrenze?year=2026` → returns:
  - realized_gains_ytd: Decimal
  - freigrenze_limit: 1000.00
  - remaining_headroom: Decimal (limit - realized)
  - status: "safe" | "warning" | "exceeded"
  - projected_tax_if_exceeded: Decimal (at estimated bracket)

**Frontend:**
- Large progress bar: €0 ──────────── €1,000
  - Green zone: 0–€700
  - Yellow zone: €700–€950
  - Red zone: €950–€1,000
  - Exceeded: dark red, shows "Alle Gewinne steuerpflichtig"
- Remaining headroom prominently displayed: "Noch €X bis zur Freigrenze"
- Cliff visualization:
  - Left side: "Bei €999 Gewinn: €0 Steuer"
  - Right side: "Bei €1.001 Gewinn: ~€450 Steuer" (at ~45% bracket)
  - Dramatic visual showing the cliff
- Pre-trade warning: "Wenn du jetzt X verkaufst, übersteigst du die Freigrenze um €Y"
- Includes only short-term gains (long-term lots are Spekulationsfrist-exempt anyway)

---

## Task 4.4.3: BMF-Schreiben Transaction Explainer

**Context:** German users are risk-averse about tax compliance. Showing exactly which BMF paragraph applies to each transaction builds trust and differentiates from every competitor.

**Depends on:** Sprint 4.3 (citation engine)

**Implementation:**
- Every transaction in the German dashboard shows a small "§" icon
- Clicking opens a tooltip/panel with:
  - The specific BMF-Schreiben paragraph number and text reference
  - Plain-German explanation of why this treatment was applied
  - For gray areas: "Hinweis: Diese Behandlung ist steuerrechtlich nicht eindeutig geklärt. Konservative Behandlung angewandt. Sprechen Sie mit Ihrem Steuerberater."
- Common examples:
  - Swap: "Tausch - steuerpflichtiges Veräußerungsgeschäft (BMF Rn. 34)"
  - Staking reward: "Sonstige Einkünfte gem. §22 Nr. 3 EStG (BMF Rn. 56)"
  - Bridge: "Kein Veräußerungsgeschäft - Übertragung zwischen eigenen Wallets"
  - LP deposit: "Umstritten - als Tausch behandelt (BMF Rn. 68, konservative Auslegung)"
