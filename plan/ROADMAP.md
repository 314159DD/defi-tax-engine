# Crypto Tax DeFi - Roadmap

**Status:** Phase 3 Complete (MVP deployed). Phase 4+ planned based on market research.
**Strategy:** US-first, DACH-second. Architect for international from day one.
**Research:** US + DACH market research complete (March 2026). See `plan/GTM.md`, `plan/MARKET_RESEARCH_SUMMARY.md`.

---

## Phase 1: Core Engine - COMPLETE

### Sprint 1: Importers + Categorizer + Calculator
- [x] Multi-chain wallet import (EVM: Ethereum, Polygon, Arbitrum, Base, Optimism + Solana)
- [x] CEX CSV importer: Coinbase, Binance, Kraken
- [x] Historical price lookup with SQLite cache (CoinGecko + DexScreener fallback)
- [x] Transaction categorization (swap, LP, stake, bridge, airdrop, NFT, self-transfer)
- [x] Known protocol address database (`src/categorizer/protocols.py`)
- [x] Cost-basis calculation: FIFO, LIFO, HIFO with tax lot management
- [x] DeFi-specific: LP tokens, wrapped tokens, staking rewards, bridges, gas fees
- [x] Holding period tracking (short-term vs long-term)
- [x] SQLite storage with incremental import and full JSON export
- [x] Test suite: categorizer, importers, storage

## Phase 2: Reporting & Web Interface - COMPLETE

### Sprint 2: Reports + Frontend + Billing
- [x] IRS Form 8949, Schedule D, income report, TurboTax CSV export
- [x] Tax loss harvesting suggestions
- [x] FastAPI backend with auth, billing, wallet, import, calculate, report routes
- [x] Quick Estimate endpoint (no auth)
- [x] Next.js 15 frontend: landing, dashboard, wallets, transactions, reports, pricing, estimate
- [x] Freemium: Free / Pro / Unlimited with Stripe billing

## Phase 3: Launch - COMPLETE

### Sprint 3.1–3.3: Deploy + Test + Verify
- [x] Docker + Railway backend, Vercel frontend
- [x] E2E integration tests + calculator tests
- [x] Wallet Connect: MetaMask + Phantom
- [x] Frontend build passing, SSR fixes, custom error pages

---

## Phase 4: Competitive Foundation - PLANNED

> These sprints transform the MVP into a product that can actually compete.
> Ordered by competitive impact, not difficulty.

### Sprint 4.1: DeFi Accuracy Overhaul
The #1 pain point across every competitor. This is our moat - get it right.
- [ ] Uniswap v3 concentrated liquidity tracking
  - [ ] NFT position detection (ERC-721 LP tokens)
  - [ ] In-range/out-of-range state tracking
  - [ ] Fee accrual tracking per position
  - [ ] Impermanent loss calculation
  - [ ] Correct cost basis on collect/close
- [ ] Cross-chain bridge cost basis preservation
  - [ ] Bridge protocol detection (Across, Stargate, Hop, Synapse, Orbiter, LayerZero)
  - [ ] Same-owner proof: matching amount + timing across chains
  - [ ] Cost basis carryover (no disposal event)
  - [ ] Gas fee attribution on both sides
- [ ] Auto-compounding vault handling
  - [ ] Yearn, Beefy, Convex vault detection
  - [ ] Share-price-based cost basis tracking
  - [ ] Reward accrual without explicit claim transactions
- [ ] Wrapped/staked token parity
  - [ ] wETH↔ETH, wBTC↔BTC, stETH↔ETH, cbETH↔ETH
  - [ ] Cost basis transfer (non-taxable conversion)
  - [ ] Rebasing token handling (stETH daily rebase = daily income events)
- [ ] Lending protocol handling
  - [ ] Aave aToken / Compound cToken interest accrual
  - [ ] Liquidation event detection and loss treatment
  - [ ] Collateral deposit/withdrawal as non-taxable
- [ ] Smart spam filter
  - [ ] Known spam token database (dust attacks, fake airdrops)
  - [ ] Zero-value transaction exclusion
  - [ ] User override: mark as spam / not spam
  - [ ] Spam tokens don't count toward transaction tier limits

### Sprint 4.2: Country Module Architecture
Abstract the tax engine so US and DE (and future countries) are pluggable.
- [ ] `src/tax/` module structure
  - [ ] `src/tax/base.py` - abstract TaxModule interface
    - `get_cost_basis_methods()` → list of allowed methods
    - `classify_holding_period(acquisition_date, disposal_date)` → short/long/exempt
    - `calculate_tax_liability(disposals, income_events)` → TaxSummary
    - `generate_report(disposals, income, year)` → ReportBundle (files + metadata)
    - `get_exemptions(disposals)` → list of exempt disposals with reason
  - [ ] `src/tax/us/` - US module (extract current logic)
    - [ ] Form 8949, Schedule D, TurboTax export (move from `src/reports/`)
    - [ ] FIFO/LIFO/HIFO all allowed
    - [ ] 1-year long-term threshold
    - [ ] Wash sale 30-day awareness
    - [ ] No exemption threshold (all gains taxable)
  - [ ] `src/tax/de/` - German module (new)
    - [ ] Anlage SO export (Finanzamt-compatible PDF + CSV)
    - [ ] FIFO only (BMF standard) - LIFO/HIFO as "what-if" comparison only
    - [ ] 1-year Spekulationsfrist → tax-free if held >365 days
    - [ ] €1,000 Freigrenze (cliff: all gains taxable if exceeded, not just excess)
    - [ ] Staking rewards as Sonstige Einkünfte (§22 EStG) at FMV on receipt
    - [ ] Personal income tax rate brackets (14–45% + 5.5% Soli)
    - [ ] WISO Steuer CSV export format
    - [ ] DATEV export format (Steuerberater-compatible)
  - [ ] Country selector in user profile + pricing page
  - [ ] Calculator engine refactor: delegates to active TaxModule for method list + holding period rules + exemptions
- [ ] Pricing page dual-mode
  - [ ] US tiers: Free / Pro $9.99mo / Unlimited $29.99mo (+ annual toggle)
  - [ ] DACH tiers: Kostenlos / Standard €49/yr / Premium €99/yr / Unbegrenzt €179/yr
  - [ ] Auto-detect from browser locale, manual override

### Sprint 4.3: Transparent Tax Logic
Both reports show trust is the #1 barrier. Users ask "will my Finanzamt/IRS accept this?"
- [ ] Tax citation engine
  - [ ] Every disposal tagged with applicable rule (IRS §1222 / BMF-Schreiben 2025 §X)
  - [ ] Every income event tagged (§61 for US, §22 Nr. 3 EStG for DE)
  - [ ] Every exemption tagged with reason + source paragraph
- [ ] Transaction detail view: "Why was this taxed this way?"
  - [ ] Expandable per-transaction explanation
  - [ ] Show cost basis method applied, lot matched, holding period calculation
  - [ ] Show which rule makes it short-term/long-term/exempt
- [ ] Report footer: methodology statement
  - [ ] US: "Calculated per IRS Revenue Ruling 2014-21, Notice 2023-34, and Form 8949 instructions"
  - [ ] DE: "Berechnet gemäß BMF-Schreiben vom 6. März 2025 (Az. IV C 1 - S 2256/24/10001 :001)"

### Sprint 4.4: German Killer Features
The features that don't exist anywhere and justify switching from CoinTracking/Blockpit.
- [ ] Spekulationsfrist dashboard
  - [ ] Per-coin, per-lot countdown: "X days until tax-free"
  - [ ] Color-coded: red (<3 months), yellow (3–9 months), green (>9 months), gold (tax-free)
  - [ ] "Safe to sell" indicator per holding
  - [ ] Historical view: which lots became tax-free this year
- [ ] Freigrenze real-time dashboard
  - [ ] Live progress bar toward €1,000 annual threshold
  - [ ] Shows realized gains YTD with running total
  - [ ] "Remaining headroom" calculation
  - [ ] Warning system: "Your next trade of X would exceed the Freigrenze"
  - [ ] Cliff visualization: shows full tax bill if threshold exceeded vs €0 if under
- [ ] BMF-Schreiben explainer per transaction
  - [ ] Each categorized transaction links to the specific BMF paragraph
  - [ ] Tooltip: German-language explanation of why this treatment applies
  - [ ] Handles gray areas honestly: "BMF-Schreiben unclear - conservative treatment applied"

### Sprint 4.5: 1099-DA Reconciliation (US Killer Feature)
Time-sensitive: millions of users received 1099-DA for first time in Feb 2026.
- [ ] 1099-DA import
  - [ ] CSV upload (Coinbase, Kraken, Binance.US formats)
  - [ ] PDF parsing fallback (OCR for scanned forms)
  - [ ] Normalize to common schema: (asset, date_acquired, date_sold, proceeds, cost_basis)
- [ ] Reconciliation engine
  - [ ] Match 1099-DA line items to on-chain transactions
  - [ ] Identify discrepancies:
    - [ ] Transactions on 1099-DA not in our data (missing import)
    - [ ] Transactions in our data not on 1099-DA (DeFi/self-custody activity)
    - [ ] Cost basis differences (exchange calculation vs ours)
    - [ ] Proceeds differences
  - [ ] Confidence scoring per match (exact, fuzzy, unmatched)
- [ ] Reconciliation report
  - [ ] Side-by-side comparison view
  - [ ] Highlighted discrepancies with explanations
  - [ ] "What to do" guidance per discrepancy type
  - [ ] Exportable reconciliation summary for CPA review

### Sprint 4.6: Landing Page & Positioning Overhaul
Current landing page is generic MVP. Needs to sell the actual differentiators.
- [ ] US landing page redesign
  - [ ] Hero: "The only crypto tax tool that gets DeFi right"
  - [ ] Privacy section: "Your data never leaves your device"
  - [ ] DeFi accuracy section: side-by-side "us vs them" for LP, bridge, staking scenarios
  - [ ] 1099-DA reconciliation CTA
  - [ ] Social proof section (when available)
  - [ ] Quick Estimate widget inline (no page navigation)
- [ ] German landing page
  - [ ] Hero: "Krypto-Steuer - lokal berechnet, nichts in der Cloud"
  - [ ] Spekulationsfrist section: "Wissen, wann steuerfrei verkauft werden kann"
  - [ ] Freigrenze section: "Nie wieder die €1.000-Grenze versehentlich überschreiten"
  - [ ] Finanzamt trust section: "BMF-konforme Berechnungen mit Quellenangabe"
  - [ ] Pricing in EUR per Steuerjahr
- [ ] Comparison pages (SEO)
  - [ ] /compare/koinly - feature table + why we're better
  - [ ] /compare/cointracker - price + DeFi accuracy
  - [ ] /compare/coinledger - privacy + DeFi
  - [ ] /compare/cointracking - modern UX + DeFi + privacy (German)
  - [ ] /compare/blockpit - price + local compute + DeFi (German)

### Sprint 4.7: Internationalization Framework
Prerequisite for German launch. Do this before Sprint 5.x content.
- [ ] i18n setup
  - [ ] next-intl or similar (not just translated strings - proper locale routing)
  - [ ] `/en/` and `/de/` route prefixes
  - [ ] Browser locale detection with manual override
  - [ ] Shared components with translation keys
- [ ] German translation
  - [ ] All UI strings (navigation, buttons, labels, tooltips)
  - [ ] All error messages
  - [ ] Tax-specific terminology (use correct Steuerrecht vocabulary)
  - [ ] Numbers/dates in German format (1.000,00 € / DD.MM.YYYY)
- [ ] Backend i18n
  - [ ] Report generation in user's locale
  - [ ] Tax citation language matches locale
  - [ ] API error messages localized

---

## Phase 5: Growth Engine - PLANNED

> Features that drive acquisition, retention, and expansion.

### Sprint 5.1: Tax Loss Harvesting Dashboard (US + DE)
- [ ] Real-time unrealized gain/loss per position
  - [ ] Current market price vs cost basis per lot
  - [ ] Sortable by largest unrealized loss (harvest candidates)
  - [ ] Filter by short-term vs long-term
- [ ] Harvest simulation
  - [ ] "If you sell X, your tax bill changes by $Y"
  - [ ] Multi-position harvest scenario builder
  - [ ] Projected savings at user's tax bracket
- [ ] Wash sale tracker (US)
  - [ ] 30-day lookback + lookahead per asset
  - [ ] Warning before selling if wash sale would apply
  - [ ] Disallowed loss tracking and basis adjustment
- [ ] Spekulationsfrist harvest optimizer (DE)
  - [ ] "Sell these lots now (short-term loss), keep those (approaching tax-free)"
  - [ ] Freigrenze-aware: "Harvest up to €X more before crossing the cliff"

### Sprint 5.2: CPA / Steuerberater Portal
Highest-ROI distribution channel per research. One CPA = dozens of clients.
- [ ] Accountant dashboard
  - [ ] Multi-client view (list of clients with status)
  - [ ] Per-client: wallets, tax summary, reports
  - [ ] Bulk report generation (all clients, selected year)
- [ ] Client management
  - [ ] Invite flow: accountant sends link, client connects wallets + grants read access
  - [ ] Permission model: accountant sees reports + summary, NOT raw transactions
  - [ ] Client can revoke access
- [ ] Export formats
  - [ ] US: Form 8949 CSV, Schedule D, TurboTax, H&R Block
  - [ ] DE: Anlage SO, WISO Steuer CSV, DATEV export
  - [ ] Branded PDF report (accountant's logo + contact info)
- [ ] Accountant pricing
  - [ ] Free tool for accountant - per-client billing ($X per client per year)
  - [ ] Volume discounts (10+, 50+, 100+ clients)
  - [ ] Stripe Connect or similar for revenue share

### Sprint 5.3: SEO Content Infrastructure
#1 acquisition channel for every competitor in both markets.
- [ ] Blog/content CMS
  - [ ] MDX-based content system in Next.js (no external CMS)
  - [ ] `/blog/` route with tag filtering
  - [ ] SEO metadata: title, description, canonical, structured data (Article schema)
  - [ ] Open Graph images auto-generated
- [ ] US content (initial batch - 15 articles)
  - [ ] Protocol tax guides: Uniswap v3, Aave, Lido, Curve, Yearn (5 articles)
  - [ ] "How to" guides: DeFi taxes, LP taxes, staking taxes, bridge taxes (4 articles)
  - [ ] 1099-DA series: what it is, how to reconcile, DeFi gaps (3 articles)
  - [ ] Competitor comparisons: vs Koinly, CoinTracker, CoinLedger (3 articles)
- [ ] DE content (initial batch - 12 articles)
  - [ ] Krypto Steuer Grundlagen: Spekulationsfrist, Freigrenze, Anlage SO (3 articles)
  - [ ] DeFi Steuer: LP, Staking, Bridges auf Deutsch (3 articles)
  - [ ] BMF-Schreiben 2025 Erklärung (1 article)
  - [ ] DAC8 Was kommt auf dich zu (1 article)
  - [ ] Vergleich: vs CoinTracking, vs Blockpit, vs Koinly, vs chain.report (4 articles)
- [ ] Sitemap, robots.txt, structured data for all pages

### Sprint 5.4: Additional Chain & Protocol Coverage
Research shows: Koinly has 80+ chains, CoinTracking 300+ integrations, Blockpit 190+ blockchains.
We have 6 chains. Need to close the gap on the most-used ones.
- [ ] EVM chains (Etherscan-compatible - low effort per chain)
  - [ ] Avalanche C-Chain (Snowtrace)
  - [ ] BNB Smart Chain (BscScan)
  - [ ] Fantom (FtmScan)
  - [ ] zkSync Era
  - [ ] Linea
  - [ ] Scroll
  - [ ] Mantle
- [ ] Non-EVM chains
  - [ ] Bitcoin (Blockstream/Mempool API) - large user base, simple tx model
  - [ ] Cosmos ecosystem (Mintscan API) - ATOM, OSMO staking
  - [ ] Near Protocol
- [ ] CEX imports (expand)
  - [ ] Gemini CSV
  - [ ] KuCoin CSV
  - [ ] OKX CSV
  - [ ] Crypto.com CSV
  - [ ] Bitpanda CSV (DACH-critical: Austrian exchange, huge in DACH)
  - [ ] Bison CSV (DACH-critical: German exchange by Börse Stuttgart)
  - [ ] Trade Republic CSV (DACH-critical: popular German neobroker)
- [ ] Protocol coverage expansion
  - [ ] Curve (vote-escrowed CRV, gauge rewards)
  - [ ] Balancer (weighted pool LP)
  - [ ] GMX (perps P&L)
  - [ ] Maker/Spark (DAI savings rate, CDP liquidations)
  - [ ] Pendle (yield tokenization)
  - [ ] Eigenlayer (restaking)
  - [ ] Jupiter (Solana aggregator)

### Sprint 5.5: Source of Funds Report
Blockpit charges €19.99 per report for this. Banks increasingly demand crypto origin proof.
- [ ] Generate "Source of Funds" documentation
  - [ ] Full transaction trail: exchange → wallet → DeFi → wallet → exchange
  - [ ] Acquisition method per holding (exchange purchase, staking reward, airdrop, etc.)
  - [ ] Timeline visualization
  - [ ] PDF export formatted for bank/exchange KYC submission
- [ ] Especially valuable in DACH (banks requesting crypto origin for large deposits)

---

## Phase 6: Retention & Network Effects - PLANNED

### Sprint 6.1: Real-Time Portfolio + Tax Position
- [ ] WebSocket-based live price feed
- [ ] Real-time portfolio valuation
- [ ] Live unrealized gain/loss per position
- [ ] Live tax liability estimate (updates as prices move)
- [ ] Push notifications: Spekulationsfrist expiring, Freigrenze approaching

### Sprint 6.2: Affiliate & Referral Program
Research shows CoinLedger's 25% recurring commission is industry-leading and drives growth.
- [ ] Referral system: unique link per user, credit on signup
- [ ] Affiliate dashboard: track clicks, signups, conversions
- [ ] Commission structure: 25% recurring (match market leader)
- [ ] Payout via Stripe Connect or PayPal

### Sprint 6.3: Mobile App (React Native)
Blockpit has mobile (iOS/Android). CoinTracking and Koinly don't. Competitive advantage in DACH.
- [ ] Portfolio view (read-only)
- [ ] Tax summary (current year)
- [ ] Spekulationsfrist countdowns (push notifications)
- [ ] Freigrenze progress
- [ ] Quick Estimate

### Sprint 6.4: Cloud Sync (Privacy-Preserving)
SQLite-only limits multi-device access. Need optional cloud with encryption.
- [ ] End-to-end encrypted Supabase sync
  - [ ] User holds the encryption key - we can't read their data
  - [ ] Sync wallet config + transaction cache + tax lots
  - [ ] Conflict resolution (last-write-wins with timestamps)
- [ ] Toggle: local-only vs encrypted cloud sync
- [ ] Clear messaging: "Your data is encrypted with your key. We cannot access it."

### Sprint 6.5: AI Transaction Categorization
Research flags AI-native competitors as the #1 strategic threat.
- [ ] LLM fallback for unknown protocols
  - [ ] Feed: raw transaction data + ABI + known patterns
  - [ ] Output: category + confidence score
  - [ ] Human override for low-confidence categorizations
- [ ] Community protocol library
  - [ ] Users can submit protocol ABI mappings
  - [ ] Verified mappings promoted to official database
  - [ ] Open-source the protocol library (community moat)

---

## Phase 7: International Expansion - FUTURE

### Sprint 7.1: UK Tax Module
- [ ] `src/tax/uk/` - HMRC Capital Gains Tax rules
- [ ] Same-day rule + 30-day bed-and-breakfast rule
- [ ] £6,000 annual exempt amount (2024/25)
- [ ] SA108 form generation

### Sprint 7.2: Australia Tax Module
- [ ] `src/tax/au/` - ATO Capital Gains Tax rules
- [ ] 50% CGT discount for assets held >12 months
- [ ] Personal use asset exemption (<$10K)
- [ ] myTax-compatible export

### Sprint 7.3: Canada Tax Module
- [ ] `src/tax/ca/` - CRA rules
- [ ] Adjusted Cost Base (ACB) method
- [ ] 50% inclusion rate for capital gains
- [ ] T1 Schedule 3 generation

### Sprint 7.4: Austrian / Swiss Variants
- [ ] `src/tax/at/` - Austrian Spekulationseinkünfte rules
- [ ] `src/tax/ch/` - Swiss Verrechnungssteuer + cantonal variations
