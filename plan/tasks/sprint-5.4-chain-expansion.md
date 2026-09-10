# Sprint 5.4: Additional Chain & Protocol Coverage

**Priority:** MEDIUM - we have 6 chains. Koinly has 80+, CoinTracking 300+, Blockpit 190+. Need to close the gap on the most-used ones.
**Depends on:** Sprint 4.1 (DeFi accuracy improvements apply to new chains too)
**Files:** `src/importers/`, `src/categorizer/protocols.py`

---

## Task 5.4.1: EVM Chains (Low Effort - Etherscan-Compatible)

Each new EVM chain reuses the existing `EVMImporter` with a different API endpoint. Effort: ~30min per chain for basic support, ~2hrs with protocol-specific categorization.

**Priority order (by user demand from research):**
1. BNB Smart Chain (BscScan) - massive DeFi ecosystem, PancakeSwap
2. Avalanche C-Chain (Snowtrace) - Trader Joe, AAVE, GMX
3. Fantom (FtmScan) - SpookySwap, Beethoven X
4. zkSync Era - growing L2
5. Linea - Consensys L2
6. Scroll - growing L2
7. Mantle - growing L2

**Implementation per chain:**
- Add chain config to `src/config.py` (API URL, API key env var, native token)
- Add chain enum value
- Add to frontend chain selector dropdown
- Add protocol addresses for that chain to `protocols.py`
- Test: import sample wallet, verify categorization

---

## Task 5.4.2: Non-EVM Chains

**Bitcoin:**
- API: Blockstream.info or Mempool.space
- Simple UTXO model: inputs/outputs
- No DeFi (just send/receive)
- Huge user base - many users have BTC + DeFi on other chains

**Cosmos:**
- API: Mintscan or LCD endpoints
- ATOM, OSMO, JUNO staking
- IBC transfers (cross-chain within Cosmos)
- Osmosis DEX swaps

**Near:**
- API: Near indexer
- Ref Finance DEX
- Staking on Near

---

## Task 5.4.3: DACH-Critical CEX Imports

These are essential for the German market - many DACH users use these exclusively:

**Bitpanda** (Austrian, huge in DACH):
- CSV export format
- Handles: crypto, stocks, metals, indices - need to filter crypto-only

**Bison** (German, by Börse Stuttgart):
- CSV export format
- Simple buy/sell/send/receive

**Trade Republic** (German neobroker):
- CSV or PDF statement
- Crypto alongside stocks/ETFs - need to filter

**Also expand:**
- Gemini CSV
- KuCoin CSV
- OKX CSV
- Crypto.com CSV

---

## Task 5.4.4: Protocol Coverage Expansion

Update `src/categorizer/protocols.py` with addresses for:
- PancakeSwap (BSC)
- Trader Joe (Avalanche)
- GMX (Arbitrum, Avalanche) - perps P&L handling
- Balancer (multi-chain) - weighted pool LP
- Curve (expanded: vote-escrow CRV, gauge system)
- Maker/Spark - DAI savings rate, CDP liquidations
- Pendle - yield tokenization
- Eigenlayer - restaking
- Jupiter (Solana) - aggregator routing
- Raydium (Solana) - concentrated liquidity (similar to Uni v3)
