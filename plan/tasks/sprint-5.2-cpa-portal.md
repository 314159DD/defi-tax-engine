# Sprint 5.2: CPA / Steuerberater Portal

**Priority:** MEDIUM-HIGH - highest-ROI distribution channel per research. One accountant = dozens of clients.
**Depends on:** Sprint 4.2 (country module for report types), Sprint 4.3 (transparent logic for CPA trust)
**Files:** New `src/web/routes/accountant.py`, new frontend `/accountant/` routes

---

## Task 5.2.1: Accountant Account Type

**Modify:** `src/web/app.py`, user profile model

- New account type: `role: "user" | "accountant"`
- Accountant profile fields: firm_name, license_number, contact_info, logo_url
- Accountant sees different dashboard (client list, not personal wallets)

---

## Task 5.2.2: Client Management

**Create:** `src/web/routes/accountant.py`

- `POST /api/accountant/invite` - generate unique invite link for client
- Client clicks link → creates account → connects wallets → grants read access to accountant
- Permission model:
  - Accountant CAN: view tax summary, download reports, see categorizations
  - Accountant CANNOT: see raw transaction details, wallet addresses, individual balances
  - Client can revoke access anytime

---

## Task 5.2.3: Multi-Client Dashboard

**Create:** `frontend/src/app/accountant/` (new route group)

- Client list: name, email, status (invited/connected/reports-ready), year, total gain/loss
- Per-client detail: tax summary, report downloads, flagged issues
- Bulk actions: "Generate all 2025 reports" → zip download

---

## Task 5.2.4: Report Branding

- White-label option: accountant's logo + firm name on report header
- PDF reports include: firm contact info, methodology statement, preparation date
- Optional: "Prepared by [Firm Name] using [Product Name]"

---

## Task 5.2.5: Export Formats

- US: Form 8949 CSV, Schedule D, TurboTax import, H&R Block import
- DE: Anlage SO PDF, WISO Steuer CSV, DATEV export
- Bundled PDF: complete client tax package (all reports + reconciliation + methodology)

---

## Task 5.2.6: Accountant Pricing

- Accountant tool is FREE (no subscription for the accountant themselves)
- Per-client billing: $X per client per tax year
- Volume discounts: 10+ clients 20% off, 50+ clients 40% off
- Stripe integration for per-client billing
- Revenue share option (accountant marks up to client, we get base fee)
