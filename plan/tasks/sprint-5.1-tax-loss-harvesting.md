# Sprint 5.1: Tax Loss Harvesting Dashboard

**Priority:** MEDIUM-HIGH - retention feature. Users come back during the year (not just tax season) to optimize.
**Depends on:** Sprint 4.2 (country module for US wash sale vs DE Spekulationsfrist logic)
**Files:** `src/reports/harvest.py` (extend), new frontend dashboard component

---

## Task 5.1.1: Real-Time Unrealized Gain/Loss

**Modify:** `src/reports/harvest.py`, new endpoint `GET /api/harvest/positions`

For each held position (open tax lots):
- Current FMV (live price lookup)
- Cost basis per lot
- Unrealized gain/loss = (current FMV × amount) - cost_basis
- Holding period classification (short/long for US, taxable/exempt for DE)
- Sort by: largest unrealized loss (default), largest gain, token name

---

## Task 5.1.2: Harvest Simulation Engine

**Create:** `src/reports/harvest_simulator.py`

User selects positions to "hypothetically sell":
- Calculate realized gain/loss for each selected position
- Apply to current year's running total
- Show projected tax impact:
  - US: at user's estimated bracket (or standard 15%/20% LTCG)
  - DE: check if harvest would push under/over Freigrenze
- Multi-position scenario: "If you sell A, B, and C, your tax bill changes by $X"

---

## Task 5.1.3: Wash Sale Tracker (US)

**Create:** `src/tax/us/wash_sale.py`

- For each asset: 30-day lookback and 30-day lookahead window
- If user sells at a loss and repurchases within window → disallowed loss
- Disallowed loss added to cost basis of replacement lot
- Warning before selling: "Selling now would trigger wash sale - loss of $X would be disallowed"
- Dashboard indicator: which positions are in a wash sale window

---

## Task 5.1.4: Spekulationsfrist Harvest Optimizer (DE)

- "Sell these lots now for a short-term loss, keep those approaching 365 days"
- Freigrenze-aware: "You can harvest €X more before crossing the €1,000 cliff"
- Combined view: Spekulationsfrist countdown + harvest opportunity per lot
