# Decision: Dual-Market Pricing Strategy

**Date:** 2026-03-26
**Status:** Proposed
**Based on:** US + DACH market research (March 2026)

## Context

The crypto tax software market uses two dominant pricing models:
- **US:** Per-tax-year one-time pricing ($49–$199 per report). No major competitor offers monthly billing.
- **DACH:** Per-Steuerjahr one-time pricing (€49–€549 per report). Germans resist monthly subscriptions (Abo-Hass culture).

## Decision

Implement dual pricing based on user's selected country:

### US Pricing - Monthly Subscription (Market Novel)
| Tier | Monthly | Annual (40% off) | Gate |
|------|---------|-------------------|------|
| Free | $0 | $0 | 100 txns, 1 wallet, ETH only, no report download |
| Pro | $9.99 | $71.88/yr | 5K txns, 5 wallets, all chains, 8949 + TurboTax |
| Unlimited | $29.99 | $215.88/yr | Unlimited + TLH + 1099-DA reconciliation |

**Why monthly for US:** No competitor does this. $9.99/mo feels cheaper than $49/year entry points. Better LTV via recurring billing. Annual toggle captures high-intent users.

### DACH Pricing - Per-Steuerjahr (Cultural Fit)
| Tier | Price | Gate |
|------|-------|------|
| Kostenlos | €0 | 100 txns, 1 Wallet, kein Download |
| Standard | €49/Steuerjahr | 1K txns, 5 Wallets, Anlage SO, WISO CSV |
| Premium | €99/Steuerjahr | 5K txns, 10 Wallets, Freigrenze-Dashboard |
| Unbegrenzt | €179/Steuerjahr | Unbegrenzt, Steuerberater-Export, DATEV |

**Why per-year for DACH:** Matches market norms (CoinTracking, Blockpit, Koinly all per-year). €179 massively undercuts Blockpit €549 for high-volume users. Steuerberater alternative costs €800–€2,500.

## Key Pricing Insights from Research

- US entry point clusters at $49 for 100 txns - our $9.99/mo undercuts by 75% at entry
- German price ceiling: ~€200–€300 before users switch to Steuerberater
- Transaction count inflation (#1 pricing complaint) - our smart spam filtering reduces perceived cost
- Free tier must show real value (estimated tax liability, gain/loss per position) not just portfolio view
- CPA/Steuerberater pricing: separate B2B tier (free tool, per-client billing) - future sprint

## Implementation

- Country selector on pricing page + in user profile
- Stripe: separate US (USD, monthly/annual) and DACH (EUR, per-year) product IDs
- Free tier identical in both markets (100 txns, 1 wallet, no download)
- Gate the report download - everything else visible for free
