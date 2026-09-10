/**
 * Abstract interface for country-specific tax modules.
 *
 * Each country module implements the rules for:
 *   - cost basis methods available
 *   - holding period classification
 *   - exemptions (e.g. German Spekulationsfrist, Freigrenze)
 *   - tax liability calculation from brackets
 *   - currency formatting
 *   - citation tagging
 *   - methodology statements
 *
 * Ported from: src/tax/base.py
 */

import Decimal from 'decimal.js';
import type { Disposal, Exemption, HoldingPeriod, IncomeCategory } from '../types';

/**
 * Abstract interface that every country tax module must implement.
 *
 * Implement this for US, DE, AT, CH, UK, AU, etc.
 */
export interface TaxModule {
  readonly countryCode: string;    // ISO 3166-1 alpha-2: "US", "DE", etc.
  readonly countryName: string;    // "United States", "Germany", etc.
  readonly currencyCode: string;   // ISO 4217: "USD", "EUR", etc.

  // ── Cost basis methods ─────────────────────────────────────────────

  /** Return list of cost basis methods available for filing (e.g. ["FIFO"]). */
  getCostBasisMethods(): string[];

  /** Return the default/recommended method for this country. */
  getDefaultMethod(): string;

  // ── Holding period classification ──────────────────────────────────

  /**
   * Classify the holding period for a single disposal.
   *
   * @param acquired - date the asset was acquired
   * @param disposed - date the asset was disposed
   * @returns HoldingPeriod enum value (SHORT_TERM, LONG_TERM, or EXEMPT)
   */
  classifyHoldingPeriod(acquired: Date, disposed: Date): HoldingPeriod;

  // ── Exemptions ─────────────────────────────────────────────────────

  /**
   * Analyze disposals and return exemptions that apply.
   *
   * @param disposals - list of Disposal objects for the year
   * @param year - tax year
   * @returns list of Exemption objects referencing specific disposals
   */
  getExemptions(disposals: Disposal[], year: number): Exemption[];

  // ── Tax liability ──────────────────────────────────────────────────

  /**
   * Calculate estimated tax liability.
   *
   * @param gains - net taxable capital gains for the year
   * @param income - total ordinary income (staking, airdrops, etc.)
   * @param userBracket - optional user-provided marginal tax rate override
   * @returns estimated tax amount as Decimal
   */
  calculateLiability(
    gains: Decimal,
    income: Decimal,
    userBracket?: Decimal,
  ): Decimal;

  // ── Currency formatting ────────────────────────────────────────────

  /**
   * Format a monetary amount for display in this country's convention.
   *
   * Examples:
   *   US: "$1,234.56"
   *   DE: "1.234,56 EUR"
   */
  formatCurrency(amount: Decimal): string;

  // ── Citation tagging ───────────────────────────────────────────────

  /**
   * Tag each disposal with the appropriate tax citation for this country.
   * Returns a new array of Disposal objects with citation fields populated.
   *
   * @param disposals - list of Disposal objects
   * @param year - tax year
   * @returns new array of Disposal objects with citation fields set
   */
  tagCitations(disposals: Disposal[], year: number): Disposal[];

  // ── Methodology ────────────────────────────────────────────────────

  /**
   * Return a methodology statement for inclusion in tax reports.
   *
   * @param method - cost basis method used, e.g. "FIFO", "LIFO", "HIFO"
   * @param year - the tax year
   * @returns Human-readable methodology statement string
   */
  getMethodologyStatement(method: string, year: number): string;

  // ── Income categories ──────────────────────────────────────────────

  /**
   * Return income categories relevant for this jurisdiction.
   * Override for country-specific categories.
   */
  getIncomeCategories(): IncomeCategory[];
}

/**
 * Default income categories common to all jurisdictions.
 * Country modules can override getIncomeCategories() for specifics.
 */
export function getDefaultIncomeCategories(): IncomeCategory[] {
  return [
    {
      name: 'Staking Rewards',
      description: 'Rewards received for staking crypto assets',
      citation: '',
    },
    {
      name: 'Airdrops',
      description: 'Tokens received via airdrop',
      citation: '',
    },
    {
      name: 'Mining Income',
      description: 'Income from mining or validating',
      citation: '',
    },
    {
      name: 'DeFi Interest',
      description: 'Interest earned from DeFi lending protocols',
      citation: '',
    },
  ];
}
