/**
 * US Tax Module -- IRS rules for cryptocurrency taxation.
 *
 * Rules:
 *   - Cost basis methods: FIFO, LIFO, HIFO (all permitted by IRS)
 *   - Holding period: <366 days = short-term, >=366 days = long-term
 *   - No exemptions (no equivalent of German Spekulationsfrist or Freigrenze)
 *   - Capital gains rates: 0%/15%/20% for long-term, ordinary income for short-term
 *   - Reports: Form 8949, Schedule D, TurboTax CSV, Income Report
 *
 * References:
 *   - IRS Publication 544 (Sales and Other Dispositions of Assets)
 *   - IRS Form 8949 instructions
 *   - Rev. Rul. 2019-24 (crypto as property)
 *   - Notice 2014-21 (crypto taxation guidance)
 *
 * Ported from: src/tax/us/module.py
 */

import Decimal from 'decimal.js';
import { HoldingPeriod } from '../../types';
import type { Disposal, Exemption, IncomeCategory } from '../../types';
import type { TaxModule } from '../base';
import { CitationCode, getCitation } from '../citations';

/** Milliseconds per day for date arithmetic. */
const MS_PER_DAY = 86_400_000;

/** Compute the difference in calendar days between two Date objects. */
function daysBetween(a: Date, b: Date): number {
  const utcA = Date.UTC(a.getFullYear(), a.getMonth(), a.getDate());
  const utcB = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate());
  return Math.round((utcB - utcA) / MS_PER_DAY);
}

export class USTaxModule implements TaxModule {
  readonly countryCode = 'US';
  readonly countryName = 'United States';
  readonly currencyCode = 'USD';

  // ── Cost basis methods ─────────────────────────────────────────────

  getCostBasisMethods(): string[] {
    return ['FIFO', 'LIFO', 'HIFO'];
  }

  getDefaultMethod(): string {
    return 'FIFO';
  }

  // ── Holding period ─────────────────────────────────────────────────

  /**
   * IRS rule: property held more than one year is long-term.
   * <366 days = short-term, >=366 days = long-term.
   */
  classifyHoldingPeriod(acquired: Date, disposed: Date): HoldingPeriod {
    const daysHeld = daysBetween(acquired, disposed);
    if (daysHeld >= 366) {
      return HoldingPeriod.LONG_TERM;
    }
    return HoldingPeriod.SHORT_TERM;
  }

  // ── Exemptions ─────────────────────────────────────────────────────

  /** US has no crypto-specific exemptions. Returns empty list. */
  getExemptions(_disposals: Disposal[], _year: number): Exemption[] {
    return [];
  }

  // ── Tax liability ──────────────────────────────────────────────────

  /**
   * Estimate US tax liability on crypto gains + income.
   *
   * This is a simplified estimate. Real US taxes depend on filing status,
   * other income, deductions, etc. We use single-filer 2025 brackets
   * as a reasonable default.
   *
   * Long-term capital gains rates (2025, single filer):
   *   0% up to $48,350
   *   15% from $48,351 to $533,400
   *   20% above $533,400
   *
   * Short-term gains are taxed as ordinary income.
   *
   * @param gains - net taxable capital gains (short + long combined for simplicity)
   * @param income - ordinary income from staking, airdrops, etc.
   * @param userBracket - optional override for marginal tax rate (e.g. new Decimal("0.37"))
   */
  calculateLiability(
    gains: Decimal,
    income: Decimal,
    userBracket?: Decimal,
  ): Decimal {
    if (userBracket !== undefined) {
      // User-provided marginal rate
      const totalTaxable = gains.plus(income);
      if (totalTaxable.lte(new Decimal('0'))) {
        return new Decimal('0');
      }
      return totalTaxable
        .mul(userBracket)
        .toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
    }

    // Default estimate: assume all gains are long-term at 15% and
    // income at 24% (median bracket). This is intentionally simplified.
    const ltRate = new Decimal('0.15');
    const stRate = new Decimal('0.24');

    const gainsTax = Decimal.max(gains, new Decimal('0')).mul(ltRate);
    const incomeTax = Decimal.max(income, new Decimal('0')).mul(stRate);
    const total = gainsTax.plus(incomeTax);

    return total.toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
  }

  // ── Citation tagging ─────────────────────────────────────────────

  /**
   * Tag each disposal with the appropriate US tax citation.
   * Returns a new array with citation fields populated.
   */
  tagCitations(disposals: Disposal[], _year: number): Disposal[] {
    return disposals.map((d) => {
      // Check for bridge transfers
      if (d.txHash && (d.holdingPeriod === 'bridge' || d.method === 'bridge')) {
        const citation = getCitation(CitationCode.US_BRIDGE_TRANSFER);
        return {
          ...d,
          citationCode: CitationCode.US_BRIDGE_TRANSFER,
          citationText: citation.text,
          citationSource: citation.source,
          isGrayArea: citation.isGrayArea,
        };
      }

      // Determine holding period classification
      const isLong =
        d.holdingPeriodEnum === HoldingPeriod.LONG_TERM ||
        d.holdingPeriod === 'long-term' ||
        d.holdingPeriod === 'long' ||
        d.holdingPeriod === 'LONG_TERM';

      if (isLong) {
        const citation = getCitation(CitationCode.US_LONG_TERM_GAIN);
        return {
          ...d,
          citationCode: CitationCode.US_LONG_TERM_GAIN,
          citationText: citation.text,
          citationSource: citation.source,
          isGrayArea: citation.isGrayArea,
        };
      }

      const citation = getCitation(CitationCode.US_SHORT_TERM_GAIN);
      return {
        ...d,
        citationCode: CitationCode.US_SHORT_TERM_GAIN,
        citationText: citation.text,
        citationSource: citation.source,
        isGrayArea: citation.isGrayArea,
      };
    });
  }

  // ── Methodology ────────────────────────────────────────────────────

  getMethodologyStatement(method: string, year: number): string {
    return (
      `This report was prepared using the ${method} cost basis method per IRS guidance ` +
      `in Notice 2014-21 and Revenue Ruling 2023-14. Cryptocurrency is treated as ` +
      `property for federal tax purposes. Capital gains and losses are reported on ` +
      `Form 8949 and Schedule D. Form 8949 categorization follows the ${year} ` +
      `Instructions for Form 8949. Income from staking, mining, and airdrops is ` +
      `reported as ordinary income at fair market value on the date of receipt. ` +
      `This report is for informational purposes only and does not constitute tax advice. ` +
      `Consult a qualified tax professional for your specific situation.`
    );
  }

  // ── Currency formatting ────────────────────────────────────────────

  /** Format as USD: $1,234.56 */
  formatCurrency(amount: Decimal): string {
    const absAmount = amount.abs();
    // Format with 2 decimal places and US-style commas
    const parts = absAmount.toFixed(2).split('.');
    const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    const formatted = `$${intPart}.${parts[1]}`;
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
        description: 'Rewards received for staking/validating',
        citation: 'IRC \u00a761; Rev. Rul. 2023-14',
      },
      {
        name: 'Airdrops',
        description: 'Tokens received via airdrop',
        citation: 'Rev. Rul. 2019-24',
      },
      {
        name: 'Mining Income',
        description: 'Income from mining or validating blocks',
        citation: 'Notice 2014-21, Q-8',
      },
      {
        name: 'DeFi Interest',
        description: 'Interest earned from DeFi lending',
        citation: 'IRC \u00a761(a)(4)',
      },
    ];
  }
}
