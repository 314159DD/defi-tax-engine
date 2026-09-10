# Sprint 4.3: Transparent Tax Logic

**Priority:** HIGH - trust is the #1 barrier in both markets. German users ask "Wird das vom Finanzamt akzeptiert?" constantly. US users question report accuracy.
**Depends on:** Sprint 4.2 (country module - citations are country-specific)
**Files:** `src/tax/`, `src/calculator/`, frontend transaction detail view

---

## Task 4.3.1: Tax Citation Database

**Create:** `src/tax/citations.py`

A mapping from tax treatment → legal citation:

US citations:
- Capital gain (short-term): "IRC §1222(1) - Short-term capital gain"
- Capital gain (long-term): "IRC §1222(3) - Long-term capital gain"
- Staking income: "Rev. Rul. 2023-14 - Staking rewards are gross income at FMV upon receipt"
- Mining income: "Notice 2014-21, Q&A 8 - Mining rewards are gross income"
- Airdrop income: "Rev. Rul. 2019-24 - Airdrop received constitutes gross income"
- Like-kind exchange: "Not applicable - IRC §1031 excludes crypto post-TCJA 2017"
- Wash sale: "IRC §1091 - Note: IRS has not formally extended wash sale rules to crypto"
- Bridge transfer: "Non-taxable - same taxpayer, same economic interest"

DE citations:
- Disposal within 1yr: "§23 Abs. 1 Satz 1 Nr. 2 EStG - Veräußerung innerhalb der Spekulationsfrist"
- Disposal after 1yr: "§23 Abs. 1 Satz 1 Nr. 2 EStG - Steuerfrei nach Ablauf der Spekulationsfrist"
- Freigrenze: "§23 Abs. 3 Satz 5 EStG - Freigrenze von 1.000 EUR"
- Staking income: "§22 Nr. 3 EStG - Sonstige Einkünfte (BMF-Schreiben 06.03.2025, Rn. 56)"
- FIFO method: "BMF-Schreiben 06.03.2025, Rn. 45 - FIFO als Verbrauchsreihenfolge"
- LP deposit: "BMF-Schreiben 06.03.2025, Rn. 68 - Tauschvorgang bei Liquiditätspool-Einlage (strittig)"

---

## Task 4.3.2: Tag Every Calculation

**Modify:** `src/calculator/engine.py`, `src/calculator/lots.py`

Every Disposal and IncomeEvent object gets a `citation` field:
- `citation_code`: e.g. "US_SHORT_TERM_GAIN", "DE_SPEKULATIONSFRIST_EXEMPT"
- `citation_text`: human-readable legal reference
- `citation_note`: optional explanation for gray areas

Gray area handling:
- When treatment is uncertain (e.g., LP deposits in DE), add:
  - `is_gray_area: true`
  - `citation_note`: "BMF-Schreiben unklar - konservative Behandlung als Tausch angewandt"
  - `alternative_treatment`: what the other interpretation would be

---

## Task 4.3.3: Transaction Detail Expansion (Frontend)

**Modify:** `frontend/src/app/transactions/page.tsx`

Add expandable detail panel per transaction:
- **Categorization:** Why this was classified as swap/LP/stake/bridge/etc.
- **Cost basis:** Which lot was matched, acquisition date, original cost
- **Holding period:** Days held, classification (short/long/exempt)
- **Tax treatment:** Citation + plain-language explanation
- **Gray areas:** Flagged with tooltip explaining the uncertainty

---

## Task 4.3.4: Report Methodology Footer

Every generated report includes a methodology statement:
- US: "This report was prepared using [FIFO/LIFO/HIFO] cost basis method per IRS guidance in Notice 2014-21 and Revenue Ruling 2023-14. Form 8949 categorization follows 2025 Instructions for Form 8949."
- DE: "Dieser Bericht wurde gemäß dem BMF-Schreiben vom 06.03.2025 (Az. IV C 1 - S 2256/24/10001 :001) unter Anwendung der FIFO-Verbrauchsreihenfolge erstellt."
