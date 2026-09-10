# Sprint 1: Core Engine - Crypto Tax

**Goal:** Build the multi-chain transaction import engine, categorize DeFi transactions, and calculate cost basis using FIFO/LIFO/HIFO methods. By end of sprint, you can import wallet transactions from EVM chains + Solana and get a cost-basis report.

**Duration:** 2 weeks
**Status:** Not Started

---

## Task 1.1: Multi-Chain Wallet Import

**Input:** Wallet addresses (EVM + Solana)
**Output:** Normalized transaction list from all supported chains

### Subtasks

- [ ] **1.1.1** Set up Python project structure:
  ```
  defi-tax-engine/
  ├── src/
  │   ├── importers/
  │   │   ├── base.py           # BaseImporter interface
  │   │   ├── evm.py            # EVM chain importer (Etherscan-like APIs)
  │   │   ├── solana.py         # Solana importer (Helius/Solscan API)
  │   │   ├── exchange.py       # CEX CSV import (Coinbase, Binance, Kraken)
  │   │   └── models.py         # RawTransaction dataclass
  │   ├── categorizer/
  │   ├── calculator/
  │   ├── reports/
  │   └── config.py
  ├── tests/
  │   └── fixtures/             # Sample transaction data
  ├── requirements.txt
  └── .env.example
  ```
- [ ] **1.1.2** Define normalized transaction model:
  ```python
  @dataclass
  class Transaction:
      tx_hash: str
      chain: str                   # ethereum, polygon, arbitrum, base, solana
      block_number: int
      timestamp: datetime
      from_address: str
      to_address: str
      tx_type: str                 # transfer, swap, lp_add, lp_remove, stake, unstake, bridge, airdrop, mint, burn
      assets_in: list[AssetTransfer]   # What the wallet received
      assets_out: list[AssetTransfer]  # What the wallet sent
      fee: AssetTransfer | None        # Gas/transaction fee
      protocol: str | None             # Uniswap, Aave, Lido, etc.
      raw_data: dict                   # Original API response

  @dataclass
  class AssetTransfer:
      token_address: str | None    # None for native (ETH, SOL)
      token_symbol: str
      amount: Decimal              # Use Decimal, never float for money
      usd_value: Decimal | None    # USD value at time of transaction
  ```
- [ ] **1.1.3** Implement EVM chain importer:
  - Support chains: Ethereum, Polygon, Arbitrum, Base, Optimism
  - Use Etherscan-compatible APIs (each chain has its own explorer API)
  - Fetch: normal transactions, internal transactions, ERC-20 transfers, ERC-721 transfers
  - Handle pagination (Etherscan returns max 10,000 per call)
  - Rate limit: 5 calls/second (free API key)
- [ ] **1.1.4** Implement Solana importer:
  - Use Helius API (free tier: 1000 req/day) or Solscan API
  - Fetch: SOL transfers, SPL token transfers, program interactions
  - Handle Solana-specific patterns: associated token accounts, system program
- [ ] **1.1.5** Implement CEX CSV importer:
  - Parse Coinbase transaction CSV export
  - Parse Binance trade history CSV export
  - Parse Kraken ledger CSV export
  - Generic CSV mapper for custom formats
- [ ] **1.1.6** Implement historical price lookup:
  - CoinGecko API: `/coins/{id}/history?date=DD-MM-YYYY`
  - Cache prices in SQLite (same token+date = same price)
  - Fallback: DexScreener API for obscure DeFi tokens
  - Handle missing prices (flag for manual entry)
- [ ] **1.1.7** Build import CLI:
  ```bash
  python -m src.import wallet 0xABC... --chain ethereum
  python -m src.import wallet 5rEq... --chain solana
  python -m src.import csv coinbase_export.csv --format coinbase
  python -m src.import csv trades.csv --format binance
  python -m src.import all --wallets wallets.json  # Import all configured wallets
  ```

**Acceptance Criteria:**
- EVM importer fetches all transaction types for a given wallet on Ethereum
- Solana importer fetches SOL + SPL token transfers
- CSV importer correctly parses Coinbase and Binance export formats
- All transactions are normalized into the common Transaction model
- Historical USD prices are resolved for 95%+ of transactions
- Prices are cached to avoid redundant API calls

---

## Task 1.2: Transaction Categorization

**Input:** Normalized transaction list
**Output:** Each transaction classified by type with DeFi-specific handling

### Subtasks

- [ ] **1.2.1** Implement transaction categorizer:
  ```python
  # categorizer/
  ├── engine.py             # Main categorization engine
  ├── rules/
  │   ├── swap.py           # DEX swap detection (Uniswap, Sushi, etc.)
  │   ├── liquidity.py      # LP add/remove detection
  │   ├── staking.py        # Stake/unstake detection (Lido, Aave, etc.)
  │   ├── bridge.py         # Cross-chain bridge detection
  │   ├── airdrop.py        # Airdrop detection (received with no send)
  │   ├── nft.py            # NFT mint/sale/transfer
  │   └── transfer.py       # Simple transfer between own wallets
  ├── protocols.py          # Known protocol address → name mapping
  └── models.py             # CategorizedTransaction
  ```
- [ ] **1.2.2** Implement swap detection:
  - Pattern: assets_out (token A) + assets_in (token B) in same transaction
  - Identify DEX protocol from contract address (Uniswap V2/V3, SushiSwap, Curve, etc.)
  - Tax event: YES (disposal of token A, acquisition of token B)
- [ ] **1.2.3** Implement liquidity provision detection:
  - LP Add: assets_out (2 tokens) + assets_in (LP token)
  - LP Remove: assets_out (LP token) + assets_in (2 tokens)
  - Tax event: Complex - need to track LP token cost basis
- [ ] **1.2.4** Implement staking detection:
  - Stake: assets_out (token) + assets_in (staked token or receipt)
  - Unstake: reverse
  - Staking rewards: assets_in only (income event)
  - Tax event: Rewards are income at receipt; stake/unstake may or may not be taxable
- [ ] **1.2.5** Implement bridge detection:
  - Pattern: assets_out on chain A, assets_in on chain B (matched by timing + amount)
  - Tax event: NO (transfer between own wallets, but track for cost basis continuity)
- [ ] **1.2.6** Implement airdrop detection:
  - Pattern: assets_in with no corresponding assets_out, no known sender
  - Tax event: YES (income at fair market value on receipt)
- [ ] **1.2.7** Implement self-transfer detection:
  - Pattern: from_address and to_address are both in user's wallet list
  - Tax event: NO (not a disposal)
- [ ] **1.2.8** Build known protocol address database:
  - Map contract addresses to protocol names (Uniswap Router, Aave Pool, etc.)
  - Use publicly available lists + Etherscan labels
  - Support user-added custom protocol mappings

**Acceptance Criteria:**
- Swaps on Uniswap V2/V3 are correctly identified and categorized
- LP add/remove events are detected and paired
- Staking rewards are separated from stake/unstake transactions
- Bridges are detected across chains (matched by timing and amount)
- Airdrops are identified as income events
- Self-transfers are correctly excluded from taxable events
- At least 90% of transactions from a typical DeFi wallet are auto-categorized

---

## Task 1.3: Cost Basis Calculation

**Input:** Categorized transactions sorted by timestamp
**Output:** Cost basis for each lot, realized gains/losses for each disposal

### Subtasks

- [ ] **1.3.1** Implement lot tracking system:
  ```python
  @dataclass
  class TaxLot:
      acquisition_date: datetime
      token: str
      amount: Decimal
      cost_basis_usd: Decimal       # Total cost basis for this lot
      cost_per_unit: Decimal         # cost_basis_usd / amount
      remaining: Decimal             # Amount not yet disposed
      source: str                    # swap, purchase, airdrop, staking_reward
      tx_hash: str

  @dataclass
  class Disposal:
      date: datetime
      token: str
      amount: Decimal
      proceeds_usd: Decimal
      cost_basis_usd: Decimal
      gain_loss_usd: Decimal
      holding_period: str            # short-term (<1 year) or long-term (>=1 year)
      lots_consumed: list[TaxLot]    # Which lots were used
      method: str                    # FIFO, LIFO, HIFO
  ```
- [ ] **1.3.2** Implement FIFO (First In, First Out):
  - Consume oldest lots first when disposing
  - Standard IRS default method
- [ ] **1.3.3** Implement LIFO (Last In, First Out):
  - Consume newest lots first
  - Often better for short-term loss harvesting
- [ ] **1.3.4** Implement HIFO (Highest In, First Out):
  - Consume highest cost basis lots first
  - Minimizes realized gains (most tax-efficient)
- [ ] **1.3.5** Handle DeFi-specific cost basis scenarios:
  - **LP tokens**: Cost basis = sum of tokens deposited. On removal, split proportionally.
  - **Wrapped tokens**: wETH/stETH = same cost basis as underlying ETH (no taxable event on wrap if IRS agrees)
  - **Staking rewards**: Cost basis = FMV at receipt (income already reported)
  - **Airdrops**: Cost basis = FMV at receipt
  - **Bridge transfers**: Cost basis carries over from source chain
  - **Gas fees**: Add to cost basis of acquisition, or deduct from proceeds of disposal
- [ ] **1.3.6** Implement holding period tracking:
  - Short-term: held < 1 year (taxed as ordinary income)
  - Long-term: held >= 1 year (taxed at preferential rates)
  - Track per-lot, not per-token
- [ ] **1.3.7** Build calculator CLI:
  ```bash
  python -m src.calculate --wallets wallets.json --method FIFO --year 2025
  python -m src.calculate --wallets wallets.json --method HIFO --year 2025
  python -m src.calculate compare --wallets wallets.json --year 2025  # Compare all methods
  ```

**Acceptance Criteria:**
- FIFO correctly consumes oldest lots first (verified with manual calculation)
- LIFO correctly consumes newest lots first
- HIFO correctly consumes highest-cost lots first
- LP token cost basis splits correctly on removal
- Gas fees are correctly attributed (added to cost basis or deducted from proceeds)
- Holding period correctly classifies short-term vs long-term
- `compare` command shows gain/loss under all 3 methods side by side

---

## Task 1.4: Data Storage & Portfolio State

**Input:** Imported transactions, calculated cost basis
**Output:** Persistent storage of all tax data, queryable by year/token/method

### Subtasks

- [ ] **1.4.1** Design SQLite schema:
  ```sql
  -- Wallets configured by user
  CREATE TABLE wallets (
      id TEXT PRIMARY KEY,
      address TEXT NOT NULL,
      chain TEXT NOT NULL,
      label TEXT,
      last_imported_at TIMESTAMP
  );

  -- Raw normalized transactions
  CREATE TABLE transactions (
      tx_hash TEXT,
      chain TEXT,
      timestamp TIMESTAMP,
      tx_type TEXT,
      protocol TEXT,
      raw_json TEXT,
      PRIMARY KEY (tx_hash, chain)
  );

  -- Tax lots (one per acquisition)
  CREATE TABLE tax_lots (
      id TEXT PRIMARY KEY,
      token TEXT,
      amount DECIMAL,
      cost_basis_usd DECIMAL,
      acquisition_date TIMESTAMP,
      remaining DECIMAL,
      source TEXT,
      tx_hash TEXT
  );

  -- Disposals (one per sale/swap/etc)
  CREATE TABLE disposals (
      id TEXT PRIMARY KEY,
      token TEXT,
      amount DECIMAL,
      proceeds_usd DECIMAL,
      cost_basis_usd DECIMAL,
      gain_loss_usd DECIMAL,
      holding_period TEXT,
      method TEXT,
      disposal_date TIMESTAMP,
      tx_hash TEXT
  );

  -- Cached prices
  CREATE TABLE price_cache (
      token TEXT,
      date TEXT,
      usd_price DECIMAL,
      source TEXT,
      PRIMARY KEY (token, date)
  );
  ```
- [ ] **1.4.2** Implement data access layer with repository pattern
- [ ] **1.4.3** Implement incremental import (only fetch new transactions since last import)
- [ ] **1.4.4** Implement data export (full database backup as JSON)

**Acceptance Criteria:**
- All transactions persist across restarts
- Incremental import only fetches new transactions
- Tax lots and disposals are stored per calculation method
- Price cache prevents redundant API calls
- Full export produces a self-contained JSON backup

---

## Sprint 1 Definition of Done

- [ ] EVM importer fetches transactions from Ethereum, Polygon, Arbitrum, Base, Optimism
- [ ] Solana importer fetches SOL + SPL token transfers
- [ ] CSV importer handles Coinbase and Binance exports
- [ ] Transaction categorizer correctly classifies swaps, LP, staking, bridges, airdrops
- [ ] FIFO, LIFO, HIFO cost basis calculation produces correct results
- [ ] DeFi-specific scenarios handled (LP tokens, wrapped tokens, staking rewards)
- [ ] All data persisted in SQLite with incremental import support
- [ ] CLI commands for import, categorize, and calculate are working
- [ ] Test suite with known transaction scenarios and expected outputs
- [ ] All code committed with type hints and Decimal math (never float for money)
