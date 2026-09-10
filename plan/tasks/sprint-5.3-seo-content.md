# Sprint 5.3: SEO Content Infrastructure

**Priority:** MEDIUM - #1 acquisition channel for every competitor. Compounds over time. Earlier = better.
**Depends on:** Sprint 4.7 (i18n for German content)
**Files:** Frontend content system, new `/blog/` routes

---

## Task 5.3.1: Content System Setup

**Create:** MDX-based blog in Next.js

- `/blog/` route: paginated article list with tag filtering
- `/blog/[slug]/` route: individual article
- MDX files in `frontend/content/blog/en/` and `frontend/content/blog/de/`
- Frontmatter: title, description, date, tags, author, locale, canonical
- Auto-generated: Open Graph images, JSON-LD Article schema, sitemap entries
- Table of contents auto-generated from headings
- Code blocks with syntax highlighting (for any technical content)

---

## Task 5.3.2: SEO Infrastructure

- `sitemap.xml` - auto-generated, includes all pages + blog posts + comparison pages
- `robots.txt` - allow all, point to sitemap
- Canonical URLs on all pages
- hreflang tags: `/en/blog/defi-taxes` ↔ `/de/blog/defi-steuern` cross-linked
- Structured data: Article, FAQ, Product, BreadcrumbList schemas
- Meta descriptions on all pages (unique, keyword-rich, <160 chars)

---

## Task 5.3.3: US Content - Initial Batch (15 Articles)

**Protocol Tax Guides (5):**
1. "How Uniswap v3 LP Positions Are Taxed (2026 Guide)"
2. "Aave Lending & Borrowing: Complete Crypto Tax Guide"
3. "Lido stETH Staking Taxes: What the IRS Expects"
4. "Curve LP Taxes: Gauge Rewards, veCRV, and Bribes"
5. "Cross-Chain Bridge Taxes: Are Bridges Taxable Events?"

**How-To Guides (4):**
6. "How to Calculate DeFi Taxes (Step-by-Step)"
7. "Crypto Tax Loss Harvesting: Complete 2026 Guide"
8. "Staking Rewards Tax Guide: Income or Capital Gains?"
9. "NFT Taxes: Buying, Selling, Minting, and Royalties"

**1099-DA Series (3):**
10. "What Is Form 1099-DA? Everything Crypto Holders Need to Know"
11. "Your 1099-DA Is Missing Your DeFi Activity - Here's What to Do"
12. "How to Reconcile Your 1099-DA With Your Full Crypto History"

**Comparison Articles (3):**
13. "[Product] vs Koinly: Which Crypto Tax Tool Is Better for DeFi?"
14. "[Product] vs CoinTracker: Price, Accuracy, and Privacy Compared"
15. "[Product] vs CoinLedger: Honest 2026 Comparison"

---

## Task 5.3.4: DE Content - Initial Batch (12 Articles)

**Grundlagen (3):**
1. "Krypto Steuern in Deutschland: Der komplette Leitfaden 2026"
2. "Spekulationsfrist Krypto: Wann ist der Verkauf steuerfrei?"
3. "Freigrenze €1.000: Was passiert, wenn du sie überschreitest?"

**DeFi Steuer (3):**
4. "DeFi Steuern Deutschland: Uniswap, Aave, Lido richtig versteuern"
5. "Staking Steuern: Sind Staking-Rewards in Deutschland steuerpflichtig?"
6. "Bridge-Transaktionen: Steuerpflichtiger Tausch oder steuerfreie Übertragung?"

**Regulierung (2):**
7. "BMF-Schreiben 2025 erklärt: Was ändert sich für Krypto-Anleger?"
8. "DAC8: Was kommt auf deutsche Krypto-Anleger zu?"

**Vergleiche (4):**
9. "[Product] vs CoinTracking: Modernes UI, bessere DeFi-Steuer, Datenschutz"
10. "[Product] vs Blockpit: Günstiger, lokal berechnet, DeFi-nativ"
11. "[Product] vs Koinly: Datenschutz und deutsche Steuerlogik im Vergleich"
12. "[Product] vs chain.report: Mehr Chains, Free-Tier, bessere UX"
