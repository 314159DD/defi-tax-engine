# Sprint 4.6: Landing Page & Positioning Overhaul

**Priority:** HIGH - current landing page is generic MVP boilerplate. Doesn't sell any of the actual differentiators identified in research.
**Depends on:** Sprint 4.7 (i18n) for German version, but US version can ship independently
**Files:** `frontend/src/app/page.tsx`, new comparison pages, new components

---

## Task 4.6.1: US Landing Page Redesign

**Modify:** `frontend/src/app/page.tsx`

Current: Generic hero + 6 feature cards + chain badges + CTA.
New: Research-informed, conversion-optimized layout.

**Sections (in order):**

1. **Hero**
   - Headline: "The only crypto tax tool that actually handles DeFi"
   - Subheadline: "Uniswap v3 LPs, cross-chain bridges, auto-compounding vaults - without phantom gains. Your data stays on your device."
   - CTA: "Try Free - No Signup Required" → Quick Estimate
   - Secondary CTA: "Upload Your 1099-DA" → Reconciliation

2. **Problem Statement**
   - "Every crypto tax tool breaks on DeFi"
   - 3-column comparison:
     - LP deposit: Koinly shows $5,000 phantom gain | We show $0 (correct)
     - Bridge: CoinTracker shows sale + purchase | We show transfer (correct)
     - Staking: ZenLedger misses rewards | We track every reward event

3. **Privacy Section**
   - "Your financial data never touches our servers"
   - Diagram: Your Device → [calculations happen here] → PDF report
   - Contrast: Competitor → [upload everything to cloud] → hope they don't get breached

4. **1099-DA Section** (time-sensitive)
   - "Got a 1099-DA from your exchange? It's probably incomplete."
   - "DeFi activity, self-custody, and cross-chain transfers aren't on it."
   - CTA: "Reconcile your 1099-DA for free"

5. **Pricing**
   - Inline pricing cards (Free / Pro $9.99mo / Unlimited $29.99mo)
   - Competitor comparison row: "Koinly $49/yr for 100 txns | We: $9.99/mo for 5,000 txns"

6. **Chain Support**
   - Visual badges: Ethereum, Polygon, Arbitrum, Base, Optimism, Solana, + "more coming"

7. **Footer CTA**
   - "Start your free tax estimate in 30 seconds"

---

## Task 4.6.2: German Landing Page

**Create:** `frontend/src/app/de/page.tsx` (or i18n route `/de/`)

**Sections:**

1. **Hero**
   - "Krypto-Steuer - lokal berechnet, nichts in der Cloud"
   - "Spekulationsfrist, Freigrenze, Anlage SO - alles automatisch. Deine Daten bleiben auf deinem Gerät."
   - CTA: "Kostenlos testen" → Quick Estimate

2. **Spekulationsfrist Section**
   - "Wisse genau, wann du steuerfrei verkaufen kannst"
   - Screenshot/mockup of countdown dashboard
   - "Per-Lot Countdown - nicht nur eine Schätzung"

3. **Freigrenze Section**
   - "Nie wieder die €1.000-Grenze versehentlich überschreiten"
   - Cliff visualization
   - "Echtzeit-Tracking deiner realisierten Gewinne"

4. **Privacy / Datenschutz**
   - "Deine Finanzdaten verlassen nie dein Gerät"
   - Contrast with cloud-based competitors
   - "Kein Upload deiner Wallet-Adressen, Salden oder Transaktionen auf fremde Server"

5. **Finanzamt-Konformität**
   - "BMF-konforme Berechnungen mit Quellenangabe"
   - "Jede Berechnung zeigt den BMF-Paragraphen"
   - BMF-Schreiben 2025 reference

6. **Pricing (EUR per Steuerjahr)**
   - Kostenlos / Standard €49 / Premium €99 / Unbegrenzt €179
   - "Günstiger als jeder Steuerberater (ab €800/Jahr)"

7. **Vergleich**
   - Quick comparison table: vs CoinTracking, vs Blockpit
   - Links to detailed comparison pages

---

## Task 4.6.3: Competitor Comparison Pages

**Create:** `frontend/src/app/compare/[competitor]/page.tsx` (dynamic route)

Pages to create:
- `/compare/koinly` - DeFi accuracy + privacy + pricing
- `/compare/cointracker` - pricing (5x cheaper) + DeFi accuracy + privacy
- `/compare/coinledger` - privacy + LP/bridge handling
- `/compare/cointracking` - modern UX + DeFi + Datenschutz (DE-focused)
- `/compare/blockpit` - local compute + pricing (€179 vs €549) + DeFi (DE-focused)

**Template per page:**
1. Feature comparison table (us vs them, checkmarks)
2. Price comparison (specific tiers)
3. DeFi accuracy comparison (specific scenarios)
4. Privacy comparison
5. CTA: "Switch to [Product] - import your data in 5 minutes"

**SEO:** Title: "[Product] vs [Competitor] - Honest Comparison [Year]"
