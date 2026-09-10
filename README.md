# DeFi Tax Engine

A privacy-first crypto tax calculator built for DeFi activity that generic exchange-only tools get wrong: multi-chain wallets, LP positions, bridges, staking, lending, and Uniswap v3 concentrated liquidity. Cost basis is computed under FIFO, LIFO, or HIFO, and results export straight to IRS Form 8949 / Schedule D or the German Anlage SO. Financial data never leaves the user's device: transactions and tax lots are computed and stored client-side in the browser (IndexedDB), with the backend handling only authentication, billing, and a rate-limited chain-data proxy.

[![Tests](https://github.com/314159DD/defi-tax-engine/actions/workflows/test.yml/badge.svg)](https://github.com/314159DD/defi-tax-engine/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![Next.js 16](https://img.shields.io/badge/Next.js-16-black?logo=next.js)

> This project was built as a complete product but has not been launched publicly. There is no live deployment, no user base, and no revenue to report here - the numbers below are counts of code and tests, not usage.

---

## How it works

```
 Wallet address / CSV export ──┐
   (16 chains, 11 exchanges)   │
                                ▼
                     Importer (per-chain / per-exchange parser)
                                │
                                ▼
                     Categorizer (rule-based DeFi classification)
                     swap, LP add/remove, stake, bridge, airdrop,
                     lending, vault, Uniswap v3, spam filtering
                                │
                                ▼
                     Cost-basis engine (FIFO / LIFO / HIFO)
                     tax lots, disposals, wash-sale flags
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              Form 8949    Anlage SO     CSV export
              Schedule D   (Germany)     (TurboTax, WISO,
              (US)                       DATEV, generic)
```

Everything above the export step runs in the browser. The FastAPI backend (`src/web/app_slim.py`) only covers Supabase auth, Stripe billing, and a server-side-keyed proxy to chain explorer / RPC APIs, so wallet keys for third-party data providers never reach the client.

An earlier iteration of the backend (`src/web/app.py`) ran the full engine server-side against a local SQLite file. It's kept in the repo for the CLI and for reference, but the client-side engine under `frontend/src/engine/` is the current architecture and mirrors the Python engine feature-for-feature.

## Supported chains

| Type | Chains |
|------|--------|
| EVM | Ethereum, Polygon, Arbitrum, Base, Optimism, BNB Chain, Avalanche, Fantom, zkSync Era, Linea, Scroll, Mantle |
| Non-EVM | Solana, Bitcoin, Cosmos Hub, Osmosis |

EVM chains are queried through Etherscan-compatible explorer APIs (one API key per chain, all optional - unset keys just mean lower rate limits). Solana goes through Helius, Bitcoin through a public Blockstream-compatible endpoint, and the two Cosmos chains through public LCD REST endpoints.

## Supported exchanges (CSV import)

Coinbase, Binance, Kraken, Bitpanda, Bison, Trade Republic, Gemini, KuCoin, OKX, Crypto.com, plus a generic CSV format for anything else.

## Categorized activity types

| Category | Types | Tax treatment |
|----------|-------|----------------|
| Taxable disposals | swap, LP remove, NFT sell, Uniswap v3 decrease-liquidity, vault withdraw, lending withdraw, lending liquidation | Capital gain/loss on disposal |
| Ordinary income | staking/lending reward, airdrop, Uniswap v3 fee collection | Income at fair market value on receipt |
| Non-taxable | transfer, bridge, stake, unstake, LP add, NFT buy, mint, approve, Uniswap v3 mint/increase/burn, vault deposit, lending deposit | Basis carried forward, no event |
| Filtered out | spam / dust tokens, unrecognized | Excluded from reports |

## Cost-basis methods

FIFO, LIFO, and HIFO, computed side by side so a user can compare outcomes before choosing a method. Each report is stamped with a methodology statement citing the relevant tax guidance (IRS Notice 2014-21 / Rev. Rul. 2023-14 for the US, the German one-year Spekulationsfrist and Section 23 EStG for Germany).

## Reports and exports

| Report | Jurisdiction | Notes |
|--------|--------------|-------|
| Form 8949 + Schedule D | US | Short-term/long-term split, box selection |
| 1099-DA reconciliation | US | Compares broker-reported basis against calculated basis |
| Wash sale report | US | Flags 30-day repurchases (not yet law for crypto, shown for awareness) |
| TurboTax / TaxAct CSV | US | Direct import format |
| Anlage SO | Germany | Private sales (Section 23 EStG), one-year holding period |
| WISO / DATEV export | Germany | Import formats for common German tax software |
| Income report | Both | Staking rewards and airdrops as ordinary income |
| Source of funds | Both | Wallet funding trail, PDF export |
| Tax loss harvesting | Both | Unrealized-loss suggestions |
| Branded PDF report | Both | Falls back to plain text if `reportlab` isn't installed |

## Quick start

### Backend

```bash
pip install -r requirements.txt
cp .env.example .env    # fill in the keys you have; all chain keys are optional
uvicorn src.web.app_slim:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev     # http://localhost:3000
```

### CLI (local SQLite engine)

```bash
python -m src.import wallet 0xABC... --chain ethereum
python -m src.calculate compare --wallets wallets.json --year 2025
python -m src.report form8949 --year 2025 --method FIFO --output form8949.csv
```

## Configuration

From [`.env.example`](.env.example):

| Variable | Required | Purpose |
|----------|----------|---------|
| `ETHERSCAN_API_KEY`, `POLYGONSCAN_API_KEY`, `ARBISCAN_API_KEY`, `BASESCAN_API_KEY`, `OPTIMISM_API_KEY` | No | Higher rate limits for the corresponding EVM chain; unset keys fall back to lower public limits |
| `HELIUS_API_KEY` | No | Solana transaction history |
| `COINGECKO_API_KEY` | No | Historical price lookup; free tier works without one |
| `SUPABASE_URL`, `SUPABASE_KEY` | Yes | User identity only, not financial data |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Yes | Subscription billing |
| `STRIPE_PRICE_PRO_MONTHLY` / `_ANNUAL`, `STRIPE_PRICE_UNLIMITED_MONTHLY` / `_ANNUAL` | Yes | Stripe Price IDs for each plan |
| `DB_PATH` | No | Overrides the local SQLite path used by the CLI engine (default `data/tax.db`) |

## Designed tiers

The product was designed around a three-tier free/paid split. It was never billed against real users, so treat this as a design artifact rather than a live pricing page:

| | Free | Pro | Unlimited |
|---|---|---|---|
| Wallets | 1 | 5 | Unlimited |
| Chains | Ethereum only | All 16 | All 16 |
| Transactions | 100 | 5,000 | Unlimited |
| Methods | FIFO | FIFO, LIFO, HIFO | FIFO, LIFO, HIFO |
| Reports | Summary only | Form 8949, Schedule D, TurboTax, Income | All, including harvest suggestions |

## Testing

512 backend test cases (`pytest`, `def test_*` across `tests/`) and 15 frontend test cases (`vitest`, in `frontend/src/engine/__tests__/`) covering the calculator, categorizer, importers, tax modules, and API layer.

```bash
pytest -q                     # backend: 512 passed
cd frontend && npm test -- --run   # frontend: 15 passed
```

CI runs both suites plus a frontend production build on every push and pull request to `main`.

## Project structure

```
src/
  importers/        Per-chain and per-exchange transaction parsers
  categorizer/       Rule-based DeFi activity classification
  calculator/         FIFO / LIFO / HIFO cost-basis engine
  tax/                 US and Germany tax logic, citations, methodology statements
  reports/            Form 8949, Schedule D, CSV/TurboTax export, harvest, source of funds
  storage/            SQLite schema and accountant/CPA portal tables
  signals/             Tax-season notification signal generator
  web/                 FastAPI app: app_slim.py (production), app.py (legacy full engine)
frontend/
  src/engine/         Client-side mirror of the Python engine (runs in a Web Worker)
  src/db/             Dexie/IndexedDB schema for local-only storage
  src/app/            Next.js routes: dashboard, wallets, reconciliation, pricing
  content/blog/       SEO content, English and German
tests/                512 backend tests, plus sample (synthetic) exchange CSVs
plan/                 Product vision, market research, architecture notes, sprint logs
```

## Disclaimer

This tool is for informational purposes only and does not constitute tax, legal, or financial advice. Tax rules for cryptocurrency vary by jurisdiction and change frequently. Verify all calculations with a qualified tax professional before filing.

## License

MIT. See [LICENSE](LICENSE).
