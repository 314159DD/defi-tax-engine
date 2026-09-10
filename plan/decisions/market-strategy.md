# Decision: US-First, DACH-Second Market Strategy

**Date:** 2026-03-26
**Status:** Approved
**Based on:** US + DACH market research (March 2026)

## The Question

Should we launch US-first, DACH-first, or both simultaneously?

## Research Findings

### US Market
- 30–45M crypto holders, 6–9M active traders
- SAM: $240M–$675M
- DeFi segment completely unserved (no accurate tool exists)
- Monthly subscription pricing is novel whitespace
- 1099-DA mandate creating millions of new forced-filers
- No dominant DeFi-native player

### DACH Market
- 6.3–7.1M crypto holders, 1.0–1.5M active traders
- SAM: €60M–€150M
- Two real incumbents (CoinTracking: complex UI, weak DeFi; Blockpit: expensive, EU-focused)
- Revenue ceiling DACH-only: €4M–€15M ARR at scale (takes years)
- Privacy (Datenschutz) is a uniquely powerful differentiator here
- Per-Steuerjahr pricing is required (cultural)
- Steuerberater B2B2C angle is underexploited

### Comparison
| Factor | US | DACH | Winner |
|--------|----|----|--------|
| Market size | 5–8x larger | Smaller | US |
| Subscription acceptance | Monthly OK | Annual only | US |
| Privacy as differentiator | Nice-to-have | Cultural value | DACH |
| DeFi user density | Higher absolute | Lower | US |
| Competition quality | Fragmented, weak DeFi | 2 strong incumbents | US |
| Regulatory urgency | 1099-DA live NOW | DAC8 exchange starts 2027 | US |
| Dev effort for localization | Already done | ~2–3 weeks for tax module | - |

## Decision

**US-first, DACH-second. Architect for both from day one.**

### Rationale
1. US market is 5–8x larger and has immediate regulatory tailwind (1099-DA)
2. No competitor owns the DeFi-native US segment - first-mover advantage available
3. DACH alone caps at €4M–€15M ARR - not enough to sustain the business independently
4. DACH expansion is ~2–3 weeks of dev work IF the architecture has a country module interface
5. Privacy positioning is strong in both markets but culturally essential in DACH

### Architecture Requirement
Tax engine must be abstracted behind `src/tax/{country}/` modules from Sprint 4.1 onward:
- `src/tax/us/` - Form 8949, Schedule D, FIFO/LIFO/HIFO, 1-year LT threshold
- `src/tax/de/` - Anlage SO, FIFO-only (BMF standard), Spekulationsfrist, Freigrenze
- Future: `src/tax/uk/`, `src/tax/au/`, `src/tax/ca/`

### Timeline
- **Weeks 1–6:** US launch (Phase 4)
- **Weeks 12–20:** DACH launch (Phase 5)
- **Week 20+:** Scale both markets simultaneously
