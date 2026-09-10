# Crypto Tax - Architecture Overview

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   Transaction Import Layer                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │
│  │ Ethereum  │  │ Polygon   │  │ Solana    │  │ CEX CSV   │    │
│  │ Etherscan │  │ Polygonscan│  │ Helius   │  │ Import    │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘    │
│        └───────────┬───┘──────────────┘──────────────┘           │
│                    ▼                                              │
│         ┌──────────────────┐     ┌──────────────┐               │
│         │  Normalizer      │────▶│ Price Lookup │               │
│         │  (→Transaction)  │     │ (CoinGecko)  │               │
│         └──────────────────┘     └──────────────┘               │
└─────────────────────┬────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Categorization Engine                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Swap     │  │ LP       │  │ Staking  │  │ Bridge   │        │
│  │ Detector │  │ Detector │  │ Detector │  │ Detector │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ Airdrop  │  │ NFT      │  │ Transfer │                      │
│  │ Detector │  │ Detector │  │ Detector │                      │
│  └──────────┘  └──────────┘  └──────────┘                      │
└─────────────────────┬────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Cost Basis Calculator                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ FIFO     │  │ LIFO     │  │ HIFO     │                      │
│  └──────────┘  └──────────┘  └──────────┘                      │
│       │              │              │                             │
│       └──────────┬───┘──────────────┘                            │
│                  ▼                                                │
│       ┌──────────────────┐                                       │
│       │ Tax Lots +       │                                       │
│       │ Disposals        │                                       │
│       └──────────────────┘                                       │
└─────────────────────┬────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Report Generation                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Form     │  │ Schedule │  │ Income   │  │ TurboTax │        │
│  │ 8949     │  │ D        │  │ Report   │  │ CSV      │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ Tax Loss Harvest │  │ Method Compare  │                      │
│  │ Suggestions      │  │ (FIFO/LIFO/HIFO)│                      │
│  └──────────────────┘  └──────────────────┘                     │
└──────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
defi-tax-engine/
├── src/
│   ├── importers/
│   │   ├── base.py              # BaseImporter interface
│   │   ├── evm.py               # EVM chain importer (Etherscan APIs)
│   │   ├── solana.py            # Solana importer (Helius)
│   │   ├── exchange.py          # CEX CSV import (Coinbase, Binance, Kraken)
│   │   ├── price.py             # Historical price lookup (CoinGecko)
│   │   └── models.py            # Transaction, AssetTransfer dataclasses
│   ├── categorizer/
│   │   ├── engine.py            # Main categorization orchestrator
│   │   ├── rules/               # Per-type detection rules
│   │   │   ├── swap.py
│   │   │   ├── liquidity.py
│   │   │   ├── staking.py
│   │   │   ├── bridge.py
│   │   │   ├── airdrop.py
│   │   │   ├── nft.py
│   │   │   └── transfer.py
│   │   ├── protocols.py         # Known protocol address → name mapping
│   │   └── models.py            # CategorizedTransaction
│   ├── calculator/
│   │   ├── engine.py            # Cost basis calculator
│   │   ├── fifo.py              # FIFO implementation
│   │   ├── lifo.py              # LIFO implementation
│   │   ├── hifo.py              # HIFO implementation
│   │   ├── lots.py              # Tax lot management
│   │   └── models.py            # TaxLot, Disposal dataclasses
│   ├── reports/
│   │   ├── form_8949.py         # IRS Form 8949 generator
│   │   ├── schedule_d.py        # Schedule D summary
│   │   ├── income_report.py     # Staking/airdrop income
│   │   ├── tax_summary.py       # High-level summary
│   │   ├── csv_export.py        # TurboTax-compatible CSV
│   │   ├── harvest.py           # Tax loss harvesting suggestions
│   │   └── models.py            # Report dataclasses
│   ├── web/
│   │   ├── app.py               # FastAPI application
│   │   ├── routes/              # API endpoints
│   │   └── database.py          # Supabase client
│   ├── storage/
│   │   ├── database.py          # SQLite setup and migrations
│   │   └── repository.py        # Data access layer
│   └── config.py
├── frontend/                     # Next.js 15 web app
│   ├── app/
│   ├── components/
│   └── lib/
├── tests/
│   └── fixtures/                # Sample transaction data
├── data/
│   └── tax.db                   # SQLite database
├── plan/
├── .env.example
└── requirements.txt
```

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | Python 3.12+ | Data processing, Decimal math, ecosystem |
| Chain Data | Etherscan APIs + Helius (Solana) | Free tiers, reliable |
| Prices | CoinGecko API (free) | No API key for basic, covers 10K+ tokens |
| Cost Basis | Custom (FIFO/LIFO/HIFO) | No good open-source DeFi cost basis library |
| Storage | SQLite | Zero infra, file-based backup |
| Backend | FastAPI | Async chain API calls, auto docs |
| Frontend | Next.js 15 + shadcn/ui | Consistent with other projects |
| Auth | Supabase Auth | Shared across PPC projects |
| Payments | Stripe | Annual + monthly subscriptions |
| Deploy | Railway (API) + Vercel (frontend) | Familiar stack |

## Critical Design Decisions

- **Decimal, never float**: All monetary values use `decimal.Decimal`. Float rounding errors accumulate and produce wrong tax numbers. This is non-negotiable.
- **Lot-based tracking**: Every acquisition creates a tax lot. Every disposal consumes lots. This is the only way to correctly calculate FIFO/LIFO/HIFO.
- **Gas fees are part of cost basis**: Gas paid on a swap increases the cost basis of the acquired token. Gas on a sale reduces proceeds.
- **Bridge is not a taxable event**: Cross-chain bridge transfers maintain cost basis continuity. The lot moves from one chain to another.
- **Self-transfers excluded**: Sending between your own wallets is not a disposal. Must detect and exclude.
- **IRS 1099-DA compliance**: New for 2026. Some brokers/exchanges will report directly to IRS. Flag which transactions are broker-reported vs self-reported.

## Tier System

| Feature | Free | Pro ($9.99/mo) | Unlimited ($29.99/mo) |
|---------|------|---------------|----------------------|
| Wallets | 1 | 5 | Unlimited |
| Chains | Ethereum only | 6 chains | All |
| Transactions | 100 | 5,000 | Unlimited |
| Methods | FIFO only | FIFO/LIFO/HIFO | FIFO/LIFO/HIFO |
| Reports | Summary | All forms | All forms |
| Harvest suggestions | -- | -- | Yes |
| Annual pricing | -- | $49.99/yr | $149.99/yr |
