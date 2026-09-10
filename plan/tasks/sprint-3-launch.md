# Sprint 3: Launch - Crypto Tax DeFi

**Goal:** Complete the core tax calculation pipeline (importers → categorizer → calculator → reports), verify deployment config, and ship to Railway + Vercel.

**Status:** Not Started
**Depends On:** Sprint 2 (API backend + frontend + Stripe billing complete)

> **Important:** The audit found that `src/importers/`, `src/categorizer/`, `src/calculator/`, and `src/reports/` directories exist but key files are missing or stubs. Before starting each task, check what's actually in the directory. Complete what exists, implement what's missing.

---

## Task 3.1: Verify and Complete EVM Chain Importer

**File:** `src/importers/evm.py`

- [ ] **3.1.1** Check `src/importers/` - list all files. Determine what's implemented vs stubbed.
- [ ] **3.1.2** If stub/missing: implement `EVMImporter`:
  ```python
  class EVMImporter:
      CHAINS = {
          "ethereum": "https://api.etherscan.io/api",
          "polygon":  "https://api.polygonscan.com/api",
          "arbitrum": "https://api.arbiscan.io/api",
          "base":     "https://api.basescan.org/api",
          "optimism": "https://api-optimistic.etherscan.io/api",
      }

      async def import_wallet(self, address: str, chain: str) -> list[RawTransaction]:
          # 1. Fetch normal txs (ETH transfers)
          # 2. Fetch ERC-20 transfers (token transfers)
          # 3. Fetch internal txs (contract interactions)
          # 4. Deduplicate by tx hash
          # 5. Return list of RawTransaction(hash, timestamp, from, to, value, token, chain)
  ```
- [ ] **3.1.3** Rate limiting: max 5 requests/second per API key (Etherscan limit). Use `asyncio.Semaphore(5)`.
- [ ] **3.1.4** Pagination: handle wallets with 10,000+ transactions (Etherscan returns max 10,000 per call - use `startblock` pagination).

**Acceptance:** `EVMImporter().import_wallet("0xd8dA...", "ethereum")` returns ≥1 transaction for a known active wallet.

---

## Task 3.2: Verify and Complete Solana Importer

**File:** `src/importers/solana.py`

- [ ] **3.2.1** Check if `src/importers/solana.py` exists and is implemented.
- [ ] **3.2.2** If stub/missing: implement `SolanaImporter` using Helius API:
  ```python
  class SolanaImporter:
      async def import_wallet(self, address: str) -> list[RawTransaction]:
          # GET https://api.helius.xyz/v0/addresses/{address}/transactions
          # Helius returns parsed transactions (swaps, transfers, NFT mints, etc.)
          # Map to RawTransaction format
  ```
- [ ] **3.2.3** Handle Helius pagination (before/limit params).
- [ ] **3.2.4** Add `HELIUS_API_KEY` requirement - if missing, return empty with warning (Solana import unavailable).

**Acceptance:** `SolanaImporter().import_wallet("So11111...")` returns transactions for a known Solana wallet.

---

## Task 3.3: Verify and Complete Transaction Categorizer

**Directory:** `src/categorizer/`

- [ ] **3.3.1** Check `src/categorizer/` - list all files.
- [ ] **3.3.2** If stub/missing: implement `TransactionCategorizer`:
  ```python
  class TransactionCategorizer:
      def categorize(self, tx: RawTransaction) -> CategorizedTransaction:
          # Returns category: swap | lp_add | lp_remove | stake | unstake |
          #                   bridge | airdrop | nft_mint | nft_sale |
          #                   transfer_in | transfer_out | fee | unknown
  ```
- [ ] **3.3.3** Categorization rules (implement in `src/categorizer/rules/`):
  - **Swap**: interacts with known DEX (Uniswap, SushiSwap, Curve, 1inch) + has both token in and token out
  - **LP add**: interacts with pool contract + receives LP token
  - **LP remove**: burns LP token + receives underlying tokens
  - **Stake**: sends token to staking contract
  - **Bridge**: sends to known bridge contract (Arbitrum bridge, Optimism bridge, etc.)
  - **Airdrop**: receives tokens from address with no prior interaction
  - **Self-transfer**: from address == to address (known own wallet) → exclude from taxable events
- [ ] **3.3.4** Known protocol address database: `src/categorizer/protocols.py`
  - Add top 50 DeFi protocol addresses (Uniswap V2/V3, Aave, Compound, Curve, Lido, etc.)
  - Format: `{"0x7a250d56...": {"name": "Uniswap V2 Router", "type": "dex"}}`

**Acceptance:** `TransactionCategorizer().categorize(swap_tx)` returns `category="swap"` for a known Uniswap transaction.

---

## Task 3.4: Verify and Complete Cost Basis Calculator

**Directory:** `src/calculator/`

- [ ] **3.4.1** Check `src/calculator/` - list all files.
- [ ] **3.4.2** If stub/missing: implement the three methods:

  **`src/calculator/fifo.py`** - First In, First Out:
  ```python
  class FIFOCalculator:
      def calculate(self, transactions: list[CategorizedTransaction]) -> list[Disposal]:
          # For each sell/swap-out event:
          # Match against the earliest acquired lot
          # Calculate gain/loss = proceeds - cost_basis
          # Track holding period (short-term < 1 year, long-term ≥ 1 year)
  ```

  **`src/calculator/lifo.py`** - Last In, First Out (same structure as FIFO, reversed)

  **`src/calculator/hifo.py`** - Highest In, First Out (match highest-cost lots first to minimize gains)

- [ ] **3.4.3** `src/calculator/lots.py` - tax lot management:
  ```python
  class TaxLot:
      token: str
      amount: Decimal
      cost_basis_usd: Decimal
      acquired_at: datetime
      tx_hash: str
  ```
- [ ] **3.4.4** DeFi-specific scenarios (implement in calculator):
  - LP tokens: when adding liquidity, record cost basis of LP token received
  - Staking rewards: taxable as income at FMV on receipt date
  - Bridges: same asset, new chain - preserve original cost basis
  - Gas fees: deductible from proceeds on sale (add to cost basis on purchase)
- [ ] **3.4.5** Wire `POST /api/calculate` in `src/web/app.py` to use the real `FIFOCalculator` (or whichever method user selected).

**Acceptance:** FIFO calculator returns correct gain/loss for a simple buy-then-sell scenario with known prices.

---

## Task 3.5: Historical Price Lookup

**File:** `src/importers/price.py`

Every cost basis calculation needs USD price at the time of transaction.

- [ ] **3.5.1** Check if `src/importers/price.py` exists.
- [ ] **3.5.2** If missing: implement `PriceLookup`:
  ```python
  class PriceLookup:
      def get_price(self, token_address: str, timestamp: int) -> Decimal:
          # 1. Check SQLite cache (data/price_cache.db)
          # 2. If not cached: fetch from CoinGecko historical API
          # 3. Cache result with 30-day TTL
          # 4. Fallback: DexScreener if CoinGecko misses obscure tokens
  ```
- [ ] **3.5.3** Handle missing prices gracefully: return `None` and flag the transaction as "price unknown" in the report (user must manually enter).

---

## Task 3.6: Verify and Complete Tax Report Generators

**Directory:** `src/reports/`

- [ ] **3.6.1** Check `src/reports/` - list all files.
- [ ] **3.6.2** Implement or complete each report generator:

  **`src/reports/form_8949.py`** - IRS Form 8949:
  ```python
  class Form8949Generator:
      def generate(self, disposals: list[Disposal]) -> list[Form8949Row]:
          # Each row: description, date_acquired, date_sold, proceeds, cost_basis, gain_loss
          # Short-term and long-term sections
  ```

  **`src/reports/schedule_d.py`** - Summary totals for Schedule D

  **`src/reports/csv_export.py`** - TurboTax-compatible CSV (same columns as TurboTax expects)

  **`src/reports/income_report.py`** - Staking rewards + airdrops as ordinary income

  **`src/reports/harvest.py`** - Tax loss harvesting suggestions:
  - Find open positions with unrealized losses
  - Suggest selling before year-end to offset gains
  - Note 30-day wash sale rule limitation

- [ ] **3.6.3** Wire all reports to API endpoints in `src/web/app.py`:
  - `GET /api/reports/form8949` → Form8949Generator output
  - `GET /api/reports/schedule_d` → ScheduleDGenerator output
  - `GET /api/reports/turbotax` → CSV export
  - `GET /api/reports/harvest` → HarvestAnalyzer suggestions (unlimited tier only)
  - All return 503 if calculate hasn't been run yet for this user

---

## Task 3.7: Supabase Schema

Check `src/web/` for database usage - if SQLite is used, determine if Supabase is needed or if SQLite is fine for MVP.

- [ ] **3.7.1** Inspect `src/web/app.py` and routes for `supabase` imports vs SQLite usage.
- [ ] **3.7.2** If Supabase: verify or create the schema:
  ```sql
  CREATE TABLE wallets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    address TEXT NOT NULL,
    chain TEXT NOT NULL,
    label TEXT,
    imported_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, address, chain)
  );

  CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    wallet_id UUID REFERENCES wallets(id),
    tx_hash TEXT NOT NULL,
    chain TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    category TEXT,
    token_in TEXT, amount_in DECIMAL,
    token_out TEXT, amount_out DECIMAL,
    usd_value DECIMAL,
    created_at TIMESTAMPTZ DEFAULT now()
  );

  CREATE TABLE tax_calculations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    tax_year INTEGER NOT NULL,
    method TEXT NOT NULL,  -- fifo, lifo, hifo
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
  );

  CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id),
    tier TEXT DEFAULT 'free',
    stripe_customer_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
  );
  ```
- [ ] **3.7.3** Add RLS: users can only access their own wallets/transactions/calculations.
- [ ] **3.7.4** If SQLite only: document this as MVP limitation, plan Supabase migration for v2.

---

## Task 3.8: Verify and Fix Deployment Config

**Note:** Dockerfile and railway.json already exist. Verify they work correctly.

- [ ] **3.8.1** Build: `docker build -t crypto-tax . && docker run -p 8000:8000 --env-file .env crypto-tax`
  - Fix any build errors
- [ ] **3.8.2** Test health endpoint: `curl http://localhost:8000/api/health` → `{"status": "ok"}`
- [ ] **3.8.3** SQLite persistence on Railway: Railway has ephemeral disk. Either:
  - Add Railway Volume mounted at `/app/data` (preferred)
  - Switch to Supabase for all persistent data
  - Document limitation in README
- [ ] **3.8.4** Frontend: `cd frontend && pnpm install && pnpm build`
  - Fix any TypeScript/build errors
- [ ] **3.8.5** Frontend .env: create `frontend/.env.example`:
  ```
  NEXT_PUBLIC_API_URL=https://your-railway-app.up.railway.app
  NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
  NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
  NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
  ```
- [ ] **3.8.6** Confirm `vercel.json` exists in `frontend/` with correct API rewrites to Railway URL.
- [ ] **3.8.7** Update `plan/ROADMAP.md`: mark Sprint 3 complete, record Railway + Vercel URLs.

---

## Acceptance Criteria (Full Sprint = MVP)

- [ ] Import wallet → transactions appear in the database
- [ ] Transactions categorized (swaps, LP, staking, etc.)
- [ ] FIFO cost basis calculation runs end-to-end without 503
- [ ] Form 8949 and TurboTax CSV downloadable
- [ ] Staking/airdrop income report available
- [ ] Tax loss harvesting suggestions shown (unlimited tier)
- [ ] `docker build` passes
- [ ] `pnpm build` passes
- [ ] ROADMAP.md updated, sprint marked complete
