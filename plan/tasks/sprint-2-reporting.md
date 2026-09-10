# Sprint 2: Reporting & Web Interface - Crypto Tax

**Goal:** Generate IRS-compliant tax forms, build a web interface for wallet connection and report viewing, and implement the freemium pricing model. By end of sprint, a user can connect wallets, view their tax summary, and download Form 8949.

**Duration:** 2 weeks
**Status:** Not Started
**Depends On:** Sprint 1 (core engine producing cost basis calculations)

---

## Task 2.1: Tax Form Generation

**Input:** Disposal records with cost basis, gains/losses, holding periods
**Output:** IRS Form 8949, Schedule D data, and 1099-DA compliance report

### Subtasks

- [ ] **2.1.1** Implement Form 8949 generation:
  ```python
  # reports/
  ├── form_8949.py          # IRS Form 8949 generator
  ├── schedule_d.py         # Schedule D summary
  ├── income_report.py      # Income from staking, airdrops, mining
  ├── tax_summary.py        # High-level tax summary
  ├── csv_export.py         # TurboTax/H&R Block compatible CSV
  └── models.py             # ReportLine, TaxSummary dataclasses
  ```
- [ ] **2.1.2** Generate Form 8949 data:
  ```python
  @dataclass
  class Form8949Line:
      description: str              # "0.5 BTC"
      date_acquired: str            # MM/DD/YYYY
      date_sold: str                # MM/DD/YYYY
      proceeds: Decimal
      cost_basis: Decimal
      gain_loss: Decimal
      holding_period: str           # 'short' or 'long'
      box: str                      # Box A (short, 1099), B (short, no 1099), D (long, 1099), E (long, no 1099)
  ```
  - Part I: Short-term capital gains/losses (held < 1 year)
  - Part II: Long-term capital gains/losses (held >= 1 year)
  - Box selection based on whether 1099 was received
- [ ] **2.1.3** Generate Schedule D summary:
  - Total short-term gains/losses
  - Total long-term gains/losses
  - Net capital gain/loss
  - Carryover loss calculation (if applicable)
- [ ] **2.1.4** Generate income report:
  - Staking rewards (ordinary income)
  - Airdrop income (ordinary income)
  - Mining/validator income (if applicable)
  - Total income by category
- [ ] **2.1.5** Implement 1099-DA compliance:
  - New IRS requirement effective 2026
  - Map each disposal to the reporting broker (if applicable)
  - Flag transactions that should appear on 1099-DA vs self-reported
- [ ] **2.1.6** Generate TurboTax-compatible CSV:
  - Format: Date, Type, Exchange, Asset, Amount, Proceeds, Cost Basis, Gain/Loss
  - Direct import into TurboTax, H&R Block, TaxAct
- [ ] **2.1.7** Generate tax loss harvesting suggestions:
  - Identify tokens with unrealized losses
  - Calculate potential tax savings from harvesting
  - Warn about wash sale rules (30-day window)
  - Sort by potential savings (largest first)
- [ ] **2.1.8** Build report CLI:
  ```bash
  python -m src.report form8949 --year 2025 --method FIFO --output form8949.csv
  python -m src.report schedule-d --year 2025
  python -m src.report income --year 2025
  python -m src.report summary --year 2025 --all-methods   # Compare FIFO/LIFO/HIFO
  python -m src.report harvest --suggestions
  python -m src.report turbotax --year 2025 --output turbotax_import.csv
  ```

**Acceptance Criteria:**
- Form 8949 CSV has correct columns and formats for IRS submission
- Short-term and long-term are correctly separated
- Schedule D totals match sum of Form 8949 lines
- Income report includes all staking rewards and airdrops
- TurboTax CSV imports successfully into TurboTax Online
- Tax loss harvesting suggestions are sorted by potential savings
- Wash sale warnings appear for harvests within 30-day window

---

## Task 2.2: Web Interface

**Input:** Backend API, UI requirements
**Output:** Next.js web app for wallet connection, tax calculation, and report download

### Subtasks

- [ ] **2.2.1** Set up FastAPI backend for web:
  ```
  src/web/
  ├── app.py              # FastAPI application
  ├── routes/
  │   ├── wallets.py      # CRUD wallet management
  │   ├── import.py       # Trigger transaction import
  │   ├── calculate.py    # Run cost basis calculation
  │   ├── reports.py      # Generate and download reports
  │   ├── auth.py         # Authentication
  │   └── billing.py      # Stripe subscription
  ├── middleware/
  └── database.py         # Supabase client
  ```
- [ ] **2.2.2** Set up Next.js 15 frontend:
  ```
  frontend/
  ├── app/
  │   ├── page.tsx              # Landing page
  │   ├── dashboard/page.tsx    # Main dashboard (wallet list, tax summary)
  │   ├── wallets/page.tsx      # Wallet management
  │   ├── reports/page.tsx      # Report generation and download
  │   ├── pricing/page.tsx      # Pricing tiers
  │   └── layout.tsx
  ├── components/
  │   ├── WalletConnect.tsx     # Add wallet (address input or WalletConnect)
  │   ├── TransactionList.tsx   # Paginated transaction table
  │   ├── TaxSummary.tsx        # Summary cards (gains, losses, income)
  │   ├── MethodComparison.tsx  # FIFO vs LIFO vs HIFO comparison
  │   ├── ReportDownload.tsx    # Download Form 8949, TurboTax CSV
  │   ├── HarvestSuggestions.tsx # Tax loss harvesting opportunities
  │   ├── PricingTable.tsx      # Tier comparison
  │   └── ImportProgress.tsx    # Transaction import progress bar
  ├── lib/
  │   ├── api.ts
  │   └── supabase.ts
  └── public/
  ```
- [ ] **2.2.3** Build dashboard:
  - Tax year selector (2024, 2025, 2026)
  - Summary cards: Total Gains, Total Losses, Net, Estimated Tax
  - Wallet list with import status and transaction counts
  - Quick actions: Import, Calculate, Download Report
- [ ] **2.2.4** Build wallet management:
  - Add wallet by address + chain
  - Label wallets (e.g., "Main ETH", "DeFi Polygon", "Trading Solana")
  - Import status indicator (last imported, transaction count)
  - Delete wallet and associated data
- [ ] **2.2.5** Build transaction viewer:
  - Paginated table with: date, type, token, amount, USD value, category
  - Filter by: chain, type, token, date range
  - Manual category override (if auto-categorization is wrong)
  - Flag transactions with missing prices for manual entry
- [ ] **2.2.6** Build report download page:
  - Cost basis method selector (FIFO/LIFO/HIFO)
  - Method comparison table (show gains under each method)
  - Download buttons: Form 8949, Schedule D, TurboTax CSV, Full JSON
  - Tax loss harvesting suggestions panel

**Acceptance Criteria:**
- User can add a wallet address, trigger import, and see transactions
- Dashboard shows accurate tax summary with gains, losses, and estimated tax
- Method comparison correctly shows different results for FIFO/LIFO/HIFO
- Reports download in correct format (CSV, JSON)
- Missing prices are flagged and allow manual entry
- Transaction categories can be manually overridden

---

## Task 2.3: Freemium Tier System

**Input:** Pricing requirements, Stripe account
**Output:** Working tier system with Stripe billing

### Subtasks

- [ ] **2.3.1** Define tier limits:
  ```python
  TIERS = {
      "free": {
          "wallets": 1,
          "chains": ["ethereum"],
          "transactions": 100,
          "methods": ["FIFO"],
          "reports": ["summary"],
          "price": 0
      },
      "pro": {
          "wallets": 5,
          "chains": ["ethereum", "polygon", "arbitrum", "base", "optimism", "solana"],
          "transactions": 5000,
          "methods": ["FIFO", "LIFO", "HIFO"],
          "reports": ["summary", "form8949", "schedule_d", "turbotax", "income"],
          "price_monthly": 9.99,
          "price_annual": 49.99
      },
      "unlimited": {
          "wallets": -1,
          "chains": "all",
          "transactions": -1,
          "methods": ["FIFO", "LIFO", "HIFO"],
          "reports": "all",
          "harvest_suggestions": True,
          "price_monthly": 29.99,
          "price_annual": 149.99
      }
  }
  ```
- [ ] **2.3.2** Implement tier enforcement in API:
  - Check tier limits before wallet add, import, and report generation
  - Return clear upgrade message when limit hit
  - Free tier: 1 wallet, Ethereum only, 100 transactions, FIFO only, summary only
- [ ] **2.3.3** Implement Stripe Checkout:
  - Pro: $9.99/month or $49.99/year (58% annual discount)
  - Unlimited: $29.99/month or $149.99/year (58% annual discount)
  - Stripe Checkout → webhook → update tier in Supabase
- [ ] **2.3.4** Implement Stripe Customer Portal for self-service
- [ ] **2.3.5** Build pricing page with feature comparison table

**Acceptance Criteria:**
- Free tier correctly limits to 1 wallet, Ethereum, 100 transactions
- Upgrade to Pro unlocks multi-chain and additional reports
- Stripe Checkout completes successfully for both monthly and annual
- Tier change reflects immediately in available features
- Pricing page clearly shows value proposition for each tier

---

## Task 2.4: Tax Season Marketing Features

**Input:** User data, tax deadline awareness
**Output:** Features that drive urgency and conversions during tax season

### Subtasks

- [ ] **2.4.1** Implement tax deadline countdown:
  - Show days remaining until April 15 filing deadline
  - Extension deadline (October 15) for those who filed extension
  - Estimated quarterly payment deadlines
- [ ] **2.4.2** Implement "Quick Estimate" (no signup required):
  - Enter wallet address → show estimated gains/losses (top-level only)
  - No login required (rate limited by IP)
  - Teaser to sign up for full report
- [ ] **2.4.3** Implement year-over-year comparison:
  - Compare 2024 vs 2025 tax liability
  - Highlight changes and trends
- [ ] **2.4.4** Generate community signal files for tax season:
  - "Tax deadline in 30 days" reminders
  - "New IRS 1099-DA requirements" educational content
  - Tax loss harvesting opportunity alerts

**Acceptance Criteria:**
- Tax deadline countdown displays correctly for current year
- Quick Estimate works without authentication
- Year-over-year comparison shows accurate delta
- Signal files generated for tax-related alerts

---

## Sprint 2 Definition of Done

- [ ] Form 8949, Schedule D, and income reports generate correctly
- [ ] TurboTax-compatible CSV exports successfully import
- [ ] Web frontend allows wallet add → import → calculate → download flow
- [ ] Method comparison shows FIFO/LIFO/HIFO side by side
- [ ] Freemium tiers enforced with Stripe billing
- [ ] Tax loss harvesting suggestions work correctly
- [ ] Quick Estimate feature works without signup
- [ ] All code committed, frontend deployed to Vercel, backend to Railway
