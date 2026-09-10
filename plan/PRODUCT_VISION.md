# Crypto Tax DeFi - Product Vision

## What

Privacy-first crypto tax calculator built for DeFi power users. Imports transactions from 6 EVM chains + Solana + major CEXs, auto-categorizes complex DeFi activity (swaps, LPs, staking, bridges, airdrops, NFTs), calculates cost basis via FIFO/LIFO/HIFO, and generates tax-ready reports. All financial data stays local in SQLite - only auth touches the cloud.

## Who Buys It

**Primary:** DeFi power users with 500+ transactions/year across multiple wallets and chains. They use Uniswap v3, Aave, Curve, Lido, cross-chain bridges. Manual tax filing is impossible for them.

**Secondary:** Active crypto traders on CEXs who need to reconcile 1099-DA forms with self-custody activity.

**Expansion (DACH):** German crypto holders who need Anlage SO reports, Spekulationsfrist tracking, and Freigrenze monitoring - and who culturally demand data privacy (Datenschutz).

## Why Now

- **1099-DA mandate (US, live 2025):** Millions of holders receiving tax forms for the first time, need reconciliation for DeFi/self-custody activity not on the form
- **DAC8 (EU, live 2026):** European exchanges now report to tax authorities - enforcement converting non-filers to customers
- **DeFi is broken everywhere:** Every competitor misclassifies LP positions, bridges, and cross-chain transfers. The #1 user complaint across all tools.
- **Privacy is uncontested:** Zero competitors offer true local-compute architecture. Cloud-only is the industry standard.
- **Market validated:** $600M–$1.5B global TAM (2025), growing 12–17% CAGR. US SAM alone $240M–$675M.

## Two Moats

1. **Privacy architecture** - financial data never leaves the user's machine. Can't be replicated by cloud-native competitors without full rewrite.
2. **DeFi accuracy** - correct handling of concentrated liquidity (Uni v3), cross-chain bridges, auto-compounding vaults, wrapped tokens. First-mover accuracy becomes a trust moat.

## Revenue Model

### US Market (Primary)
| Tier | Price | Includes |
|------|-------|---------|
| Free | $0 | 1 wallet, 100 txns, Ethereum only, portfolio view + tax estimate (no download) |
| Pro | $9.99/mo | 5 wallets, 5K txns, all chains, Form 8949 + TurboTax export |
| Unlimited | $29.99/mo | Unlimited everything + tax loss harvesting + 1099-DA reconciliation |

### DACH Market (Expansion)
| Tier | Price | Includes |
|------|-------|---------|
| Kostenlos | €0 | 1 Wallet, 100 Txns, Ethereum, Steuervorschau |
| Standard | €49/Steuerjahr | 5 Wallets, 1K Txns, Anlage SO, WISO CSV |
| Premium | €99/Steuerjahr | 10 Wallets, 5K Txns, Freigrenze-Dashboard, Spekulationsfrist-Tracker |
| Unbegrenzt | €179/Steuerjahr | Alles unbegrenzt + Steuerberater-Export + DATEV |

## Revenue Targets

- **Year 1:** $3K–$8K MRR ($36K–$96K ARR) - US DeFi niche
- **Year 2:** $15K–$40K MRR ($180K–$480K ARR) - US growth + DACH launch
- **Year 3:** $50K–$150K MRR ($600K–$1.8M ARR) - dual-market, CPA partnerships, SEO compounding

## Strategic Sequence

**US-first, DACH-second, architect for both from day one.**

The US market is 5–8x larger, accepts monthly subscriptions, and has no dominant DeFi-native player. DACH is the strongest international expansion market because German tax rules are complex (= software-requiring), incumbents have clear weaknesses, and Datenschutz culture makes privacy-first positioning uniquely powerful there.
