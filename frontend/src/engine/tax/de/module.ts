/**
 * German Tax Module -- EStG rules for cryptocurrency taxation.
 *
 * Key rules:
 *   - Cost basis: FIFO only (BMF guidance)
 *   - Spekulationsfrist: crypto held >365 days is tax-exempt (section 23 Abs. 1 EStG)
 *   - Freigrenze: if total short-term gains < EUR 1,000, ALL gains exempt
 *     (CLIFF -- if total >= EUR 1,000, ALL gains are taxable, section 23 Abs. 3 Satz 5 EStG)
 *   - Progressive tax brackets (14-45%) + Solidaritaetszuschlag (5.5%)
 *   - Staking rewards: Sonstige Einkuenfte (section 22 Nr. 3 EStG)
 *
 * Tax brackets 2025/2026 (Grundtabelle, single filer):
 *   - 0% up to EUR 11,784 (Grundfreibetrag)
 *   - 14-24% zone: EUR 11,785 - EUR 17,005
 *   - 24-42% zone: EUR 17,006 - EUR 66,760
 *   - 42% zone: EUR 66,761 - EUR 277,825
 *   - 45% zone (Reichensteuer): above EUR 277,825
 *   - Plus 5.5% Solidaritaetszuschlag on tax amount
 *
 * Ported from: src/tax/de/module.py
 */

import Decimal from 'decimal.js';
import { HoldingPeriod } from '../../types';
import type { Disposal, Exemption, IncomeCategory, TaxLot } from '../../types';
import { createExemption } from '../../types';
import type { TaxModule } from '../base';
import { CitationCode, getCitation } from '../citations';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Freigrenze threshold -- section 23 Abs. 3 Satz 5 EStG */
const FREIGRENZE = new Decimal('1000');

/** German progressive tax brackets 2025/2026 */
const GRUNDFREIBETRAG = new Decimal('11784');
const ZONE2_END = new Decimal('17005');
const ZONE3_END = new Decimal('66760');
const ZONE4_END = new Decimal('277825');

/** Solidaritaetszuschlag rate */
const SOLI_RATE = new Decimal('0.055');

/** Milliseconds per day for date arithmetic. */
const MS_PER_DAY = 86_400_000;

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Compute the difference in calendar days between two Date objects. */
function daysBetween(a: Date, b: Date): number {
  const utcA = Date.UTC(a.getFullYear(), a.getMonth(), a.getDate());
  const utcB = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate());
  return Math.round((utcB - utcA) / MS_PER_DAY);
}

/** Check if a disposal is short-term based on its holdingPeriod field. */
function isShortTerm(d: Disposal): boolean {
  if (d.holdingPeriodEnum === HoldingPeriod.SHORT_TERM) return true;
  const hp = d.holdingPeriod;
  return hp === 'short-term' || hp === 'short' || hp === 'SHORT_TERM';
}

/** Check if a disposal is exempt based on its holdingPeriod field. */
function isExempt(d: Disposal): boolean {
  if (d.holdingPeriodEnum === HoldingPeriod.EXEMPT) return true;
  const hp = d.holdingPeriod;
  return hp === 'exempt' || hp === 'EXEMPT';
}

/**
 * Calculate German income tax (Einkommensteuer) per section 32a EStG.
 *
 * Uses the 2025/2026 Grundtabelle (single filer).
 * Returns the tax amount (before Soli).
 *
 * The formula uses the official BMF calculation zones:
 *   Zone 1: 0 - 11,784 EUR -> 0% (Grundfreibetrag)
 *   Zone 2: 11,785 - 17,005 EUR -> 14-24% progressive
 *   Zone 3: 17,006 - 66,760 EUR -> 24-42% progressive
 *   Zone 4: 66,761 - 277,825 EUR -> 42% flat
 *   Zone 5: > 277,825 EUR -> 45% flat (Reichensteuer)
 */
function calculateGermanIncomeTax(taxableIncome: Decimal): Decimal {
  if (taxableIncome.lte(GRUNDFREIBETRAG)) {
    return new Decimal('0');
  }

  if (taxableIncome.lte(ZONE2_END)) {
    // Zone 2: linear interpolation 14% -> 24%
    const y = taxableIncome.minus(new Decimal('11784')).div(new Decimal('10000'));
    const tax = new Decimal('922.98').mul(y).plus(new Decimal('1400')).mul(y);
    return tax.toDecimalPlaces(0, Decimal.ROUND_HALF_UP);
  }

  if (taxableIncome.lte(ZONE3_END)) {
    // Zone 3: linear interpolation 24% -> 42%
    const z = taxableIncome.minus(new Decimal('17005')).div(new Decimal('10000'));
    const tax = new Decimal('181.19')
      .mul(z)
      .plus(new Decimal('2397'))
      .mul(z)
      .plus(new Decimal('1025.38'));
    return tax.toDecimalPlaces(0, Decimal.ROUND_HALF_UP);
  }

  if (taxableIncome.lte(ZONE4_END)) {
    // Zone 4: flat 42%
    const tax = new Decimal('0.42').mul(taxableIncome).minus(new Decimal('10636.31'));
    return tax.toDecimalPlaces(0, Decimal.ROUND_HALF_UP);
  }

  // Zone 5: Reichensteuer 45%
  const tax = new Decimal('0.45').mul(taxableIncome).minus(new Decimal('18972.06'));
  return tax.toDecimalPlaces(0, Decimal.ROUND_HALF_UP);
}

// ---------------------------------------------------------------------------
// Spekulationsfrist and Freigrenze helper types
// ---------------------------------------------------------------------------

export interface SpekulationsfristLotData {
  token: string;
  amount: string;
  acquisitionDate: string;
  spekulationsfristEnd: string;
  daysRemaining: number;
  isExempt: boolean;
}

export interface FreigrenzeStatus {
  realizedGainsYtd: string;
  limit: string;
  remaining: string;
  status: 'under' | 'over';
}

// ---------------------------------------------------------------------------
// GermanTaxModule
// ---------------------------------------------------------------------------

export class GermanTaxModule implements TaxModule {
  readonly countryCode = 'DE';
  readonly countryName = 'Germany';
  readonly currencyCode = 'EUR';

  // ── Cost basis methods ─────────────────────────────────────────────

  /** FIFO is the only method accepted by German tax authorities (BMF). */
  getCostBasisMethods(): string[] {
    return ['FIFO'];
  }

  getDefaultMethod(): string {
    return 'FIFO';
  }

  /** Additional methods available for what-if analysis (not for filing). */
  getComparisonMethods(): string[] {
    return ['FIFO', 'LIFO', 'HIFO'];
  }

  // ── Holding period ─────────────────────────────────────────────────

  /**
   * German Spekulationsfrist:
   * - Held >365 days -> EXEMPT (tax-free, section 23 Abs. 1 Satz 1 Nr. 2 EStG)
   * - Held <=365 days -> SHORT_TERM (taxable as private Veraeusserungsgeschaeft)
   *
   * Note: Germany uses >365 days (not >=366). Held exactly 365 days = still taxable.
   * Held 366 days = exempt.
   */
  classifyHoldingPeriod(acquired: Date, disposed: Date): HoldingPeriod {
    const daysHeld = daysBetween(acquired, disposed);
    if (daysHeld > 365) {
      return HoldingPeriod.EXEMPT;
    }
    return HoldingPeriod.SHORT_TERM;
  }

  // ── Exemptions ─────────────────────────────────────────────────────

  /**
   * Apply German exemptions:
   *
   * 1. Spekulationsfrist (section 23 Abs. 1 EStG):
   *    Disposals with holding period > 365 days are tax-exempt.
   *
   * 2. Freigrenze (section 23 Abs. 3 Satz 5 EStG):
   *    If total SHORT-TERM gains for the year < EUR 1,000,
   *    ALL short-term disposals are exempt.
   *    If total >= EUR 1,000, ALL short-term gains are taxable (CLIFF!).
   */
  getExemptions(disposals: Disposal[], year: number): Exemption[] {
    const exemptions: Exemption[] = [];

    // Filter to the requested year
    const yearDisposals = disposals.filter((d) => {
      const dYear = new Date(d.date).getFullYear();
      return dYear === year;
    });

    // 1. Spekulationsfrist exemptions
    for (const d of yearDisposals) {
      if (isExempt(d)) {
        exemptions.push(
          createExemption({
            disposalId: d.txHash,
            reason: 'Spekulationsfrist (held > 365 days)',
            citationCode: '\u00a723 Abs. 1 Satz 1 Nr. 2 EStG',
            citationText:
              'Private Veraeusserungsgeschaefte bei Kryptowaehrungen: ' +
              'Steuerfreiheit nach Ablauf der Spekulationsfrist von einem Jahr.',
            exemptAmount: d.gainLossUsd, // full gain is exempt
          }),
        );
      }
    }

    // 2. Freigrenze check for short-term disposals
    const shortTermDisposals = yearDisposals.filter(isShortTerm);
    let totalShortTermGains = new Decimal('0');
    for (const d of shortTermDisposals) {
      if (d.gainLossUsd.gt(new Decimal('0'))) {
        totalShortTermGains = totalShortTermGains.plus(d.gainLossUsd);
      }
    }

    // CLIFF: total < 1000 = ALL exempt; total >= 1000 = ALL taxable
    if (
      totalShortTermGains.lt(FREIGRENZE) &&
      totalShortTermGains.gt(new Decimal('0'))
    ) {
      for (const d of shortTermDisposals) {
        if (d.gainLossUsd.gt(new Decimal('0'))) {
          exemptions.push(
            createExemption({
              disposalId: d.txHash,
              reason: `Freigrenze: total short-term gains (${totalShortTermGains.toFixed(2)} EUR) < 1,000 EUR`,
              citationCode: '\u00a723 Abs. 3 Satz 5 EStG',
              citationText:
                'Freigrenze fuer private Veraeusserungsgeschaefte: ' +
                'Gewinne bleiben steuerfrei, wenn der aus den privaten ' +
                'Veraeusserungsgeschaeften erzielte Gesamtgewinn im ' +
                'Kalenderjahr weniger als 1.000 Euro betragen hat.',
              exemptAmount: d.gainLossUsd,
            }),
          );
        }
      }
    }

    return exemptions;
  }

  // ── Tax liability ──────────────────────────────────────────────────

  /**
   * Calculate German tax liability on crypto gains + income.
   *
   * @param gains - net taxable short-term gains (exempt gains already excluded)
   * @param income - ordinary income from staking/airdrops (Sonstige Einkuenfte)
   * @param userBracket - optional override marginal rate
   * @returns Total tax including Solidaritaetszuschlag
   */
  calculateLiability(
    gains: Decimal,
    income: Decimal,
    userBracket?: Decimal,
  ): Decimal {
    if (userBracket !== undefined) {
      const totalTaxable = Decimal.max(gains.plus(income), new Decimal('0'));
      const tax = totalTaxable
        .mul(userBracket)
        .toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
      const soli = tax.mul(SOLI_RATE).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
      return tax.plus(soli);
    }

    const totalTaxable = Decimal.max(gains.plus(income), new Decimal('0'));
    const tax = calculateGermanIncomeTax(totalTaxable);
    const soli = tax.mul(SOLI_RATE).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
    return tax.plus(soli);
  }

  // ── Citation tagging ─────────────────────────────────────────────

  /**
   * Tag each disposal with the appropriate German tax citation.
   * Considers Spekulationsfrist, Freigrenze cliff, LP deposits, and bridges.
   * Returns a new array with citation fields populated.
   */
  tagCitations(disposals: Disposal[], year: number): Disposal[] {
    // Filter to the requested year for Freigrenze calculation
    const yearDisposals = disposals.filter((d) => {
      const dYear = new Date(d.date).getFullYear();
      return dYear === year;
    });

    // Calculate total short-term gains for Freigrenze check
    const shortTermDisposals = yearDisposals.filter(isShortTerm);
    let totalShortTermGains = new Decimal('0');
    for (const d of shortTermDisposals) {
      if (d.gainLossUsd.gt(new Decimal('0'))) {
        totalShortTermGains = totalShortTermGains.plus(d.gainLossUsd);
      }
    }
    const freigrenzeUnder =
      totalShortTermGains.lt(FREIGRENZE) &&
      totalShortTermGains.gt(new Decimal('0'));

    return disposals.map((d) => {
      // Check for bridge transfers
      if (d.holdingPeriod === 'bridge' || d.method === 'bridge') {
        const citation = getCitation(CitationCode.DE_BRIDGE_TRANSFER);
        return {
          ...d,
          citationCode: CitationCode.DE_BRIDGE_TRANSFER,
          citationText: citation.text,
          citationSource: citation.source,
          isGrayArea: citation.isGrayArea,
        };
      }

      // Check for LP deposits (gray area)
      // Use method field or holdingPeriod as proxy for source/tx_type detection
      if (d.method === 'lp_add' || d.method === 'lp_deposit') {
        const citation = getCitation(CitationCode.DE_LP_DEPOSIT_GRAY_AREA);
        return {
          ...d,
          citationCode: CitationCode.DE_LP_DEPOSIT_GRAY_AREA,
          citationText: citation.text,
          citationSource: citation.source,
          isGrayArea: citation.isGrayArea,
        };
      }

      // Determine holding period
      if (isExempt(d)) {
        // Spekulationsfrist exempt (held > 1 year)
        const citation = getCitation(CitationCode.DE_SPEKULATIONSFRIST_EXEMPT);
        return {
          ...d,
          citationCode: CitationCode.DE_SPEKULATIONSFRIST_EXEMPT,
          citationText: citation.text,
          citationSource: citation.source,
          isGrayArea: citation.isGrayArea,
        };
      }

      // Short-term -- check Freigrenze
      let citation;
      let code: CitationCode;
      if (freigrenzeUnder && d.gainLossUsd.gt(new Decimal('0'))) {
        citation = getCitation(CitationCode.DE_FREIGRENZE_EXEMPT);
        code = CitationCode.DE_FREIGRENZE_EXEMPT;
      } else if (!freigrenzeUnder && totalShortTermGains.gte(FREIGRENZE)) {
        citation = getCitation(CitationCode.DE_FREIGRENZE_EXCEEDED);
        code = CitationCode.DE_FREIGRENZE_EXCEEDED;
      } else {
        citation = getCitation(CitationCode.DE_SPEKULATIONSFRIST_TAXABLE);
        code = CitationCode.DE_SPEKULATIONSFRIST_TAXABLE;
      }

      return {
        ...d,
        citationCode: code,
        citationText: citation.text,
        citationSource: citation.source,
        isGrayArea: citation.isGrayArea,
      };
    });
  }

  // ── Methodology ────────────────────────────────────────────────────

  getMethodologyStatement(method: string, year: number): string {
    return (
      `Dieser Bericht wurde gem\u00e4\u00df dem BMF-Schreiben vom 06.03.2025 ` +
      `(Az. IV C 1 - S 2256/24/10001 :001) unter Anwendung der ` +
      `${method}-Verbrauchsreihenfolge erstellt. ` +
      `Kryptow\u00e4hrungen gelten als private Verm\u00f6gensgegenst\u00e4nde i.S.d. ` +
      `\u00a723 EStG. Ver\u00e4u\u00dferungen innerhalb der einj\u00e4hrigen ` +
      `Spekulationsfrist unterliegen der Einkommensteuer (\u00a723 Abs. 1 Satz 1 Nr. 2 EStG). ` +
      `Die Freigrenze betr\u00e4gt 1.000 EUR (\u00a723 Abs. 3 Satz 5 EStG). ` +
      `Staking-Ertr\u00e4ge werden als sonstige Eink\u00fcnfte gem. \u00a722 Nr. 3 EStG erfasst. ` +
      `Steuerjahr: ${year}. ` +
      `Dieser Bericht dient ausschlie\u00dflich der Information und ersetzt keine ` +
      `steuerliche Beratung durch einen Steuerberater.`
    );
  }

  // ── Currency formatting ────────────────────────────────────────────

  /** Format as EUR with German locale: 1.234,56 EUR */
  formatCurrency(amount: Decimal): string {
    const absAmount = amount.abs().toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
    // Format with US locale first (commas as thousands sep)
    const parts = absAmount.toFixed(2).split('.');
    const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const formatted = `${intPart},${parts[1]} \u20ac`;
    if (amount.isNeg()) {
      return `-${formatted}`;
    }
    return formatted;
  }

  // ── Income categories ──────────────────────────────────────────────

  getIncomeCategories(): IncomeCategory[] {
    return [
      {
        name: 'Staking Rewards',
        description: 'Einkuenfte aus Staking von Kryptowaehrungen',
        citation: '\u00a722 Nr. 3 EStG',
      },
      {
        name: 'Airdrops',
        description: 'Einkuenfte aus Airdrops',
        citation: '\u00a722 Nr. 3 EStG',
      },
      {
        name: 'Mining',
        description: 'Einkuenfte aus Mining (ggf. gewerblich)',
        citation: '\u00a715 EStG / \u00a722 Nr. 3 EStG',
      },
      {
        name: 'DeFi-Zinsen',
        description: 'Zinsen aus DeFi-Lending-Protokollen',
        citation: '\u00a720 Abs. 1 Nr. 7 EStG / \u00a722 Nr. 3 EStG',
      },
    ];
  }

  // ── German-specific public helpers ─────────────────────────────────

  /**
   * Return the Freigrenze status for the user.
   *
   * @returns Object with realized gains YTD, limit, remaining headroom, and status.
   */
  getFreigrenzeStatus(disposals: Disposal[], year: number): FreigrenzeStatus {
    const yearDisposals = disposals.filter((d) => {
      const dYear = new Date(d.date).getFullYear();
      return dYear === year;
    });

    let shortTermGains = new Decimal('0');
    for (const d of yearDisposals) {
      if (isShortTerm(d) && d.gainLossUsd.gt(new Decimal('0'))) {
        shortTermGains = shortTermGains.plus(d.gainLossUsd);
      }
    }

    const remaining = Decimal.max(FREIGRENZE.minus(shortTermGains), new Decimal('0'));
    const status = shortTermGains.lt(FREIGRENZE) ? 'under' : 'over';

    return {
      realizedGainsYtd: shortTermGains.toString(),
      limit: FREIGRENZE.toString(),
      remaining: remaining.toString(),
      status,
    };
  }

  /**
   * Return per-lot data with Spekulationsfrist info.
   *
   * @param lots - list of TaxLot objects
   * @returns List of per-lot Spekulationsfrist data
   */
  getSpekulationsfristData(lots: TaxLot[]): SpekulationsfristLotData[] {
    const today = new Date();
    const todayStr = today.toISOString().slice(0, 10);

    return lots.map((lot) => {
      const acqDate = new Date(lot.acquisitionDate);
      // End date = 1 year + 1 day after acquisition (the first exempt day)
      // Handle Feb 29 edge case
      let endYear = acqDate.getFullYear() + 1;
      let endMonth = acqDate.getMonth();
      let endDay = acqDate.getDate();
      if (acqDate.getMonth() === 1 && acqDate.getDate() === 29) {
        // Feb 29 -> Mar 1 next year
        endMonth = 2; // March (0-indexed)
        endDay = 1;
      }
      const endDate = new Date(Date.UTC(endYear, endMonth, endDay));
      const endDateStr = endDate.toISOString().slice(0, 10);

      const daysRemaining = Math.max(
        daysBetween(today, endDate),
        0,
      );

      return {
        token: lot.token,
        amount: lot.remaining.toString(),
        acquisitionDate: lot.acquisitionDate,
        spekulationsfristEnd: endDateStr,
        daysRemaining,
        isExempt: daysRemaining === 0,
      };
    });
  }
}
