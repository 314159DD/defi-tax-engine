# Sprint 4.2: Country Module Architecture

**Priority:** HIGH - prerequisite for German market, US/DE pricing split, and all future country expansions.
**Depends on:** Sprint 1–3 (existing US logic to extract)
**Files:** `src/tax/` (new), `src/reports/` (refactor), `src/calculator/engine.py` (refactor), `src/web/app.py`, frontend pricing + dashboard

---

## Why

The entire tax engine is currently US-hardcoded. German rules are fundamentally different (FIFO-only, 1-year exemption, €1,000 cliff threshold, Anlage SO instead of Form 8949). We need a clean abstraction before building any country-specific features.

---

## Task 4.2.1: Tax Module Interface

**Create:** `src/tax/base.py`

```python
class TaxModule(ABC):
    country_code: str  # "US", "DE", "AT", "CH", "UK", "AU"

    def get_cost_basis_methods(self) -> list[str]
    def get_default_method(self) -> str
    def classify_holding_period(self, acquired: date, disposed: date) -> HoldingPeriod
    def get_exemptions(self, disposals: list[Disposal]) -> list[Exemption]
    def calculate_liability(self, disposals, income_events, user_profile) -> TaxSummary
    def generate_reports(self, disposals, income_events, year) -> list[ReportFile]
    def get_income_categories(self) -> list[IncomeCategory]
    def format_currency(self, amount: Decimal) -> str
```

**Create:** `src/tax/models.py` - shared types: HoldingPeriod, Exemption, TaxSummary, ReportFile, IncomeCategory

---

## Task 4.2.2: Extract US Module

**Create:** `src/tax/us/__init__.py`, `src/tax/us/module.py`, `src/tax/us/reports.py`

Move existing logic from `src/reports/` into US module:
- `form_8949.py` → `src/tax/us/form_8949.py`
- `schedule_d.py` → `src/tax/us/schedule_d.py`
- `csv_export.py` → `src/tax/us/turbotax_export.py`
- `income_report.py` → `src/tax/us/income_report.py`
- `harvest.py` stays shared (both markets need it)

US-specific rules:
- `get_cost_basis_methods()` → ["FIFO", "LIFO", "HIFO", "SPEC_ID"]
- `classify_holding_period()` → short-term if <366 days, else long-term
- `get_exemptions()` → [] (no exemptions in US)
- Wash sale tracking (30-day rule)

---

## Task 4.2.3: Build German Module

**Create:** `src/tax/de/__init__.py`, `src/tax/de/module.py`, `src/tax/de/reports.py`, `src/tax/de/anlage_so.py`, `src/tax/de/wiso_export.py`, `src/tax/de/datev_export.py`

German-specific rules:
- `get_cost_basis_methods()` → ["FIFO"] (BMF standard)
- `get_comparison_methods()` → ["FIFO", "LIFO", "HIFO"] (what-if only, not for filing)
- `classify_holding_period()`:
  - Held >365 days → EXEMPT (Spekulationsfrist, §23 Abs. 1 Satz 1 Nr. 2 EStG)
  - Held ≤365 days → TAXABLE
- `get_exemptions()`:
  - Check total annual gains from private disposals
  - If total < €1,000 → ALL disposals exempt (Freigrenze, §23 Abs. 3 Satz 5 EStG)
  - If total ≥ €1,000 → ALL disposals taxable (cliff, not deduction)
  - Spekulationsfrist exemptions per lot
- `calculate_liability()`:
  - Apply personal income tax brackets (14–45%) + Solidaritätszuschlag (5.5% of tax)
  - Staking rewards = Sonstige Einkünfte (separate from capital gains)
- Reports: Anlage SO PDF/CSV, WISO Steuer CSV, DATEV export

---

## Task 4.2.4: Calculator Engine Refactor

**Modify:** `src/calculator/engine.py`

Current: engine hardcodes FIFO/LIFO/HIFO selection and 1-year holding period.
New: engine delegates to active TaxModule:
- Methods list comes from `module.get_cost_basis_methods()`
- Holding period classification from `module.classify_holding_period()`
- Exemption checking from `module.get_exemptions()` after calculation

---

## Task 4.2.5: API + Frontend Country Support

**Modify:** `src/web/app.py`
- Add `country` field to user profile
- Tax calculation endpoint accepts `country` parameter
- Report generation delegates to correct TaxModule
- Pricing endpoint returns tiers based on country

**Modify:** Frontend
- Country selector in settings/profile
- Pricing page: auto-detect locale, show correct tiers
- Dashboard: show correct currency, holding period labels, exemption status
- Report page: show correct report types (Form 8949 for US, Anlage SO for DE)
