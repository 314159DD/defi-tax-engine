# Sprint 4.5: 1099-DA Reconciliation

**Priority:** HIGH - time-sensitive. Millions of US users received 1099-DA for first time in Feb 2026. This is a unique acquisition moment.
**Depends on:** Sprint 4.2 (US tax module)
**Files:** `src/tax/us/`, new frontend reconciliation view

---

## Context

Starting 2025 tax year, centralized exchanges issue 1099-DA forms reporting gross proceeds. For 2026 onwards, cost basis is included. BUT: DeFi activity, self-custody transfers, and cross-chain activity do NOT appear on 1099-DA. Users who have both CEX and DeFi activity now face a reconciliation problem - the 1099-DA doesn't match their complete picture.

No competitor offers a dedicated reconciliation tool. This is a pure acquisition feature.

---

## Task 4.5.1: 1099-DA Import

**Create:** `src/importers/form_1099da.py`

**Supported formats:**
- Coinbase 1099-DA CSV (likely: date_sold, date_acquired, proceeds, cost_basis, gain_loss, asset)
- Kraken 1099-DA CSV
- Binance.US 1099-DA CSV
- Generic CSV with column mapping UI
- PDF upload with OCR parsing (stretch goal - use pytesseract or similar)

**Normalize to schema:**
```python
@dataclass
class Form1099DAEntry:
    asset: str
    date_acquired: date | None  # may be "VARIOUS"
    date_sold: date
    proceeds: Decimal
    cost_basis: Decimal | None  # not required for 2025
    gain_loss: Decimal | None
    broker_name: str
    is_covered: bool  # covered vs uncovered security
```

---

## Task 4.5.2: Reconciliation Engine

**Create:** `src/tax/us/reconciliation.py`

**Matching logic:**
1. For each 1099-DA entry, find matching disposal in our calculated data
2. Match criteria: same asset + same disposal date (±1 day tolerance) + proceeds within 2% tolerance
3. Confidence scoring:
   - EXACT_MATCH: date + asset + proceeds all match
   - FUZZY_MATCH: date ±1 day OR proceeds within 5%
   - UNMATCHED_1099: entry on 1099-DA but not in our data (user missing an import)
   - UNMATCHED_OURS: disposal in our data but not on 1099-DA (DeFi/self-custody activity)

**Discrepancy types:**
- `MISSING_IMPORT`: 1099-DA has a transaction we don't - user needs to import that exchange
- `DEFI_NOT_ON_1099`: we have DeFi disposals that the exchange doesn't know about - user must self-report
- `COST_BASIS_DIFF`: our cost basis differs from exchange's - often because cross-wallet transfers affect lot ordering
- `PROCEEDS_DIFF`: rare - usually rounding differences

**Output:**
```python
@dataclass
class ReconciliationResult:
    matched: list[MatchedEntry]  # our disposal ↔ 1099-DA entry
    unmatched_1099: list[Form1099DAEntry]  # on form, not in our data
    unmatched_ours: list[Disposal]  # in our data, not on form
    discrepancies: list[Discrepancy]  # matched but values differ
    summary: ReconciliationSummary  # totals, confidence score
```

---

## Task 4.5.3: Reconciliation UI

**Create:** `frontend/src/app/reconciliation/` (new page)

**Layout:**
1. Upload zone: drag-and-drop 1099-DA file
2. After upload: side-by-side comparison table
   - Left column: 1099-DA entries
   - Right column: our calculated disposals
   - Color coding: green (matched), yellow (fuzzy), red (unmatched/discrepancy)
3. Discrepancy detail panel:
   - What's different
   - Why it's different (plain English explanation)
   - "What to do" guidance:
     - MISSING_IMPORT → "Import your [exchange] transactions to resolve"
     - DEFI_NOT_ON_1099 → "This DeFi activity must be self-reported on Form 8949"
     - COST_BASIS_DIFF → "Your cost basis may differ because [reason]. Use our calculation for accuracy."
4. Export: reconciliation summary PDF for CPA review

---

## Task 4.5.4: Marketing Integration

- Quick Estimate page: add "Upload your 1099-DA for a free reconciliation preview"
- Landing page: "Fix your 1099-DA before the IRS does it for you" CTA
- Free tier: allow 1099-DA upload + reconciliation summary (no detailed report without paid tier)
