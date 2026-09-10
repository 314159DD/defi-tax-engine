# Tech Stack Decisions - Crypto Tax

## Decision Log

### 1. Python with Decimal for all monetary math

**Decision:** Python with `decimal.Decimal` for all financial calculations. Never use float.
**Date:** 2026-03-24
**Status:** Accepted (non-negotiable)

**Context:** Tax calculations must be accurate to the cent. IEEE 754 floating point introduces rounding errors that compound across thousands of transactions.

**Example of why float fails:**
```python
# Float: WRONG
>>> 0.1 + 0.2
0.30000000000000004

# Decimal: CORRECT
>>> Decimal('0.1') + Decimal('0.2')
Decimal('0.3')
```

**Rules:**
- All `amount`, `cost_basis`, `proceeds`, `gain_loss` fields are `Decimal`
- All price lookups return `Decimal`
- JSON serialization: use `str(decimal_value)`, deserialize with `Decimal(string_value)`
- Never, ever use float for money. Code review should reject any float in financial code.

---

### 2. SQLite for local storage (not Supabase for data)

**Decision:** SQLite for transaction data and tax calculations. Supabase only for auth and user metadata.
**Date:** 2026-03-24
**Status:** Accepted

**Context:** Users' financial data is sensitive. Minimizing server-side storage reduces liability.

**Rationale:**
- Financial transaction data stays local (privacy-first)
- SQLite handles 100K+ transactions without issue
- File-based backup (users can export/backup their `.db` file)
- No server-side storage of financial data reduces compliance burden
- Supabase Auth handles user identity; Supabase DB stores only tier/subscription info

**Trade-off:**
- Users can't access from multiple devices (local-only)
- Acceptable for V1. Cloud sync is a future feature.

---

### 3. Etherscan-compatible APIs for EVM chains

**Decision:** Use chain-specific Etherscan-compatible APIs for transaction data
**Date:** 2026-03-24
**Status:** Accepted

**Context:** Need transaction history for multiple EVM chains.

**Chain → API mapping:**
| Chain | API | Free Limit |
|-------|-----|-----------|
| Ethereum | api.etherscan.io | 5/sec |
| Polygon | api.polygonscan.com | 5/sec |
| Arbitrum | api.arbiscan.io | 5/sec |
| Base | api.basescan.org | 5/sec |
| Optimism | api-optimistic.etherscan.io | 5/sec |

**Rationale:**
- All use the same API format (one importer with chain-specific base URLs)
- Free tier is sufficient for personal use (5 calls/second)
- Returns: normal txs, internal txs, ERC-20 transfers, ERC-721 transfers

**Alternative considered:**
- Alchemy/Infura: More powerful but costs money and requires more complex parsing
- The Graph: Good for protocol-specific data, but overkill for transaction history

---

### 4. Helius API for Solana

**Decision:** Helius API for Solana transaction data
**Date:** 2026-03-24
**Status:** Accepted

**Context:** Solana has a different transaction model. Need a specialized API.

**Rationale:**
- Helius is the leading Solana data provider
- Free tier: 1000 requests/day (sufficient for personal use)
- `getTransactionsByAddress` returns enriched transaction data
- Handles SPL token transfers, program interactions, and staking
- Already used by RP2 (open-source crypto tax tool)

---

### 5. CoinGecko for historical prices

**Decision:** CoinGecko free API for historical token prices
**Date:** 2026-03-24
**Status:** Accepted

**Context:** Every transaction needs a USD value at the time of execution.

**Rationale:**
- Free API (demo key): 10-30 calls/minute
- Covers 10,000+ tokens including most DeFi tokens
- `/coins/{id}/history?date=DD-MM-YYYY` gives daily price
- Cache aggressively - same token + same date = same price forever

**Fallback chain:**
1. CoinGecko (primary)
2. DexScreener API (for obscure DeFi tokens not on CoinGecko)
3. Manual entry (user inputs price for unresolvable tokens)

---

### 6. Custom cost basis engine (not RP2)

**Decision:** Build custom cost basis calculator, not use RP2
**Date:** 2026-03-24
**Status:** Accepted

**Context:** RP2 is an excellent open-source crypto tax tool. Should we build on it or build our own?

**Rationale for custom:**
- RP2 is a CLI tool, not a library. Hard to integrate into a web app.
- RP2 doesn't handle DeFi-specific scenarios well (LP tokens, wrapped tokens, bridges)
- Our categorizer feeds directly into our calculator (tight integration)
- We need real-time recalculation when method changes (FIFO → HIFO)
- RP2's plugin architecture adds complexity we don't need

**What we learn from RP2:**
- Lot-based tracking is the right approach
- FIFO/LIFO/HIFO are the methods that matter
- Their test cases are valuable reference material

---

### 7. Freemium pricing with annual tax season focus

**Decision:** Low monthly prices with strong annual discounts, timed for tax season
**Date:** 2026-03-24
**Status:** Accepted

**Context:** Crypto tax tools have highly seasonal demand. Most users need the tool once a year.

**Pricing strategy:**
- Free tier exists to convert users during tax panic
- Annual pricing is the real play ($49.99/yr Pro, $149.99/yr Unlimited)
- Monthly exists for users who want to try before committing
- Tax deadline urgency drives conversion (countdown timer on pricing page)

**Comparison to competitors:**
| Tool | Price | Our Advantage |
|------|-------|--------------|
| Koinly | $49-279/year | We're cheaper, DeFi-focused |
| CoinTracker | $59-599/year | We handle DeFi edge cases better |
| TokenTax | $65-3,499/year | Much cheaper for individuals |
| CryptoTaxCalculator | $49-399/year | Comparable, we compete on DeFi accuracy |

---

### 8. FastAPI for backend (async chain calls)

**Decision:** FastAPI for the web API backend
**Date:** 2026-03-24
**Status:** Accepted

**Context:** Transaction import involves many concurrent API calls to chain explorers.

**Rationale:**
- Native async: import from 5 chains simultaneously with `asyncio.gather()`
- Each chain import does 10-50 API calls. Sequential = minutes. Concurrent = seconds.
- Consistent with the team's other backend services, which also use FastAPI
- Auto-generated OpenAPI docs for API documentation
