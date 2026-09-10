# Sprint 4.1: DeFi Accuracy Overhaul

**Priority:** CRITICAL - #1 user pain point across all competitors. This is our moat.
**Depends on:** Sprint 1 (categorizer engine, calculator engine, protocol database)
**Files:** `src/categorizer/`, `src/calculator/`, `src/categorizer/protocols.py`

---

## Why This Sprint First

Every Reddit thread, every Trustpilot review, both market research reports say the same thing: DeFi tracking is broken everywhere. LP positions generate phantom gains, bridges are treated as sales, auto-compounding vaults are invisible. If we get this right, we have a real product. If we don't, we're just another broken tool.

---

## Task 4.1.1: Uniswap v3 Concentrated Liquidity

**Context:** Uni v3 positions are ERC-721 NFTs (not fungible LP tokens like v2). Each position has a specific price range. Fees accrue separately from the position value. No competitor handles this correctly.

**Files to create/modify:**
- `src/categorizer/rules/uniswap_v3.py` (new)
- `src/calculator/engine.py` (extend for NFT-based LP positions)
- `src/calculator/lots.py` (extend TaxLot for LP NFTs)

**Implementation:**
1. Detect Uni v3 NFT mints via NonfungiblePositionManager contract interactions
2. Extract: token0, token1, tickLower, tickUpper, liquidity, fee tier
3. Track position lifecycle: mint → increaseLiquidity → decreaseLiquidity → collect → burn
4. Cost basis = sum of token0 + token1 deposited at FMV on deposit date
5. Fee collection = income event at FMV on collect date
6. Position close (full decrease + burn): disposal at FMV of withdrawn tokens, gain/loss vs cost basis
7. Impermanent loss calculation: compare actual withdrawal value vs "just held" value

**Test cases:**
- Mint position ETH/USDC 1800–2200 range → hold → collect fees → close
- Partial decrease (remove 50% liquidity)
- Out-of-range position (100% converted to one token)
- Multiple increases to same position

---

## Task 4.1.2: Cross-Chain Bridge Cost Basis Preservation

**Context:** When users bridge ETH from Ethereum to Arbitrum, every competitor treats it as a sale + purchase (phantom gain). It's a self-transfer - cost basis should carry over.

**Files to create/modify:**
- `src/categorizer/rules/bridge.py` (extend)
- `src/categorizer/protocols.py` (add bridge protocol addresses)
- `src/calculator/engine.py` (bridge = non-taxable transfer)

**Implementation:**
1. Expand bridge protocol detection: Across, Stargate, Hop, Synapse, Orbiter, LayerZero, Wormhole, Multichain
2. Match bridge transactions across chains:
   - Same token (or canonical equivalent: USDC.e ↔ USDC)
   - Amount match within tolerance (bridge fees)
   - Timing match (within bridge protocol's typical delay: 1min–30min)
3. Link source tx (chain A) → destination tx (chain B) as transfer pair
4. Cost basis carries from source lot to destination lot
5. Bridge fee = deductible expense (add to cost basis of received tokens)
6. Gas fees on both chains = deductible

**Test cases:**
- ETH: Ethereum → Arbitrum via Across (fast bridge, ~2min)
- USDC: Polygon → Base via Stargate (canonical token mismatch USDC.e → USDC)
- Failed bridge: source tx exists, destination never arrived (edge case)

---

## Task 4.1.3: Auto-Compounding Vault Handling

**Context:** Yearn/Beefy/Convex vaults auto-compound rewards. Users deposit token, receive vault share. Share price increases over time. There's no explicit "reward claim" transaction.

**Files to create/modify:**
- `src/categorizer/rules/vault.py` (new)
- `src/calculator/engine.py` (share-price tracking)

**Implementation:**
1. Detect vault deposit: token_out = underlying, token_in = vault share (yvDAI, mooX, etc.)
2. Track vault share cost basis = FMV of deposited tokens
3. On withdrawal: vault shares → underlying tokens
4. Gain/loss = (withdrawal FMV - deposit FMV) - this is the compounded yield
5. Tax treatment: capital gain (US) / depends on holding period (DE)
6. Need vault share price at deposit + withdrawal time (query vault contract or use DeFiLlama)

**Test cases:**
- Deposit 1000 DAI into yvDAI → wait → withdraw 1050 DAI (5% yield)
- Partial withdrawal
- Multiple deposits at different times, single withdrawal

---

## Task 4.1.4: Wrapped/Staked Token Parity

**Context:** wETH↔ETH, stETH↔ETH, cbETH↔ETH. These are non-taxable conversions (same economic asset). Rebasing tokens (stETH) generate daily income events.

**Files to modify:**
- `src/categorizer/rules/swap.py` (exclude wrapped token pairs from swaps)
- `src/calculator/engine.py` (cost basis transfer for wraps)
- New: `src/data/token_pairs.py` - canonical equivalence map

**Implementation:**
1. Maintain equivalence map: {wETH: ETH, stETH: ETH, cbETH: ETH, wBTC: BTC, ...}
2. Wrap/unwrap: cost basis transfers, no taxable event
3. stETH rebase: daily balance increase = income event at FMV of increase
4. cbETH: exchange-rate-based (not rebase), gain calculated on unwrap

**Test cases:**
- Wrap 1 ETH → 1 wETH (no tax event, cost basis carries)
- stETH daily rebase: 10 stETH → 10.001 stETH next day (0.001 income at FMV)
- cbETH unwrap: 1 cbETH → 1.05 ETH (0.05 ETH gain)

---

## Task 4.1.5: Lending Protocol Handling

**Files to create/modify:**
- `src/categorizer/rules/lending.py` (new)
- `src/calculator/engine.py` (interest accrual)

**Implementation:**
1. Detect Aave aToken / Compound cToken deposits (collateral = non-taxable deposit)
2. Interest accrual: aTokens rebase (like stETH); cTokens appreciate in exchange rate
3. Withdrawal: gain = (withdrawn - deposited), taxed as interest income
4. Liquidation: forced sale at market price, loss = (proceeds - cost basis)
5. Borrowing: not a taxable event (it's a loan, not income)

---

## Task 4.1.6: Smart Spam Filter

**Context:** Users report 100 "real" trades but 800+ counted transactions from spam tokens, dust attacks, fake airdrops. This inflates their tier and bill.

**Files to create:**
- `src/categorizer/spam.py` (new)
- `src/data/spam_tokens.py` (known spam token list)

**Implementation:**
1. Known spam token database (top 500 known spam contracts per chain)
2. Heuristic detection:
   - Token with no liquidity on any DEX
   - Token name contains suspicious patterns ("Visit X.com", "Claim at", etc.)
   - Dust amount (<$0.01 FMV)
   - Airdropped to >10K addresses in same block
3. Auto-flag as spam (user can override)
4. Spam transactions excluded from:
   - Transaction tier count (don't bill for spam)
   - Tax calculations (no phantom income from spam airdrops)
   - Dashboard totals
5. Spam inbox: separate view where user can review and un-flag

**Test cases:**
- Known spam token airdrop → auto-flagged, not counted
- Legitimate small airdrop (real token, small amount) → not flagged
- User manually un-flags → included in calculations
