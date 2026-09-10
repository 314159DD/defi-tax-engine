/**
 * Tax loss harvesting - unrealized position analysis and harvest suggestions.
 *
 * Ported from src/reports/harvest.py.
 *
 * Strategy:
 *   1. Find open tax lots with current market value < cost basis (unrealized losses)
 *   2. Calculate potential tax savings based on holding period and estimated tax rate
 *   3. Warn about wash sale rule (IRS 30-day window before/after sale)
 *   4. Sort suggestions by potential savings (highest first)
 *   5. Provide full unrealized position view for dashboard
 *
 * IMPORTANT: IRS has NOT definitively ruled on crypto wash sales as of 2026.
 * We warn users but do not enforce. The 30-day rule may apply in future guidance.
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import { HoldingPeriod } from '../types';

// Estimated marginal tax rates - user should override with actual rates
const SHORT_TERM_RATE = new Decimal('0.37');
const LONG_TERM_RATE = new Decimal('0.20');
const LONG_TERM_DAYS = 365;
const SPEKULATIONSFRIST_DAYS = 365;

// ---------------------------------------------------------------------------
// UnrealizedPosition - real-time dashboard view
// ---------------------------------------------------------------------------

export interface UnrealizedPosition {
  token: string;
  lotId: string;
  amount: Decimal;
  costBasis: Decimal;
  currentValue: Decimal;
  unrealizedGainLoss: Decimal;
  holdingPeriod: HoldingPeriod;
  acquisitionDate: string; // ISO date
  daysHeld: number;
  // DE-specific fields
  spekulationsfristRemaining: number | null;
  isTaxFree: boolean;
}

/** Tax lot input shape for the unrealized position calculator. */
export interface TaxLotInput {
  id: string;
  token: string;
  amount: Decimal;
  costBasisUsd: Decimal;
  acquisitionDate: string; // ISO date
  remaining: Decimal;
}

/**
 * Build unrealized position list from open tax lots and current prices.
 *
 * @param taxLots       - Array of open tax lots
 * @param currentPrices - Map of token symbol (upper) -> current USD/EUR price
 * @param country       - "US" or "DE" - affects holding period classification
 * @param asOfDate      - Date to calculate from (default: today)
 * @returns             List sorted by unrealized_gain_loss ascending (largest losses first)
 */
export function getUnrealizedPositions(
  taxLots: TaxLotInput[],
  currentPrices: Record<string, Decimal>,
  country: string = 'US',
  asOfDate?: string, // ISO date
): UnrealizedPosition[] {
  const today = asOfDate
    ? new Date(asOfDate.slice(0, 10) + 'T00:00:00Z')
    : new Date();

  const positions: UnrealizedPosition[] = [];

  for (const lot of taxLots) {
    if (lot.remaining.lte('0')) continue;

    const token = lot.token.toUpperCase();
    const currentPrice = currentPrices[token];
    if (currentPrice === undefined) continue;

    if (lot.amount.lte('0')) continue;

    const costPerUnit = lot.costBasisUsd.div(lot.amount);
    const costOfRemaining = lot.remaining.times(costPerUnit);
    const currentValue = lot.remaining.times(currentPrice);
    const unrealized = currentValue.minus(costOfRemaining);

    // Parse acquisition date
    let acqDate: Date;
    try {
      acqDate = new Date(lot.acquisitionDate.slice(0, 10) + 'T00:00:00Z');
      if (isNaN(acqDate.getTime())) continue;
    } catch {
      continue;
    }

    const daysHeld = Math.floor(
      (today.getTime() - acqDate.getTime()) / 86400000,
    );

    // Holding period classification depends on country
    let hp: HoldingPeriod;
    if (country === 'DE') {
      hp = daysHeld > SPEKULATIONSFRIST_DAYS
        ? HoldingPeriod.EXEMPT
        : HoldingPeriod.SHORT_TERM;
    } else {
      hp = daysHeld >= 366
        ? HoldingPeriod.LONG_TERM
        : HoldingPeriod.SHORT_TERM;
    }

    // DE-specific: Spekulationsfrist remaining days
    let spekRemaining: number | null = null;
    let isTaxFree = false;
    if (country === 'DE') {
      const spekEndDays = SPEKULATIONSFRIST_DAYS + 1 - daysHeld;
      spekRemaining = Math.max(spekEndDays, 0);
      isTaxFree = spekRemaining === 0;
    }

    positions.push({
      token,
      lotId: lot.id,
      amount: lot.remaining,
      costBasis: costOfRemaining,
      currentValue,
      unrealizedGainLoss: unrealized,
      holdingPeriod: hp,
      acquisitionDate: lot.acquisitionDate.slice(0, 10),
      daysHeld,
      spekulationsfristRemaining: spekRemaining,
      isTaxFree,
    });
  }

  // Sort by unrealized gain/loss ascending (largest losses first)
  positions.sort((a, b) =>
    a.unrealizedGainLoss.cmp(b.unrealizedGainLoss),
  );

  return positions;
}

// ---------------------------------------------------------------------------
// HarvestSuggestion (original, kept for backward compatibility)
// ---------------------------------------------------------------------------

export interface HarvestSuggestion {
  token: string;
  lotId: string;
  amountRemaining: Decimal;
  costBasisPerUnit: Decimal;
  currentPriceUsd: Decimal;
  unrealizedLossUsd: Decimal;
  holdingPeriod: string; // "short" | "long"
  potentialTaxSavings: Decimal;
  washSaleWarning: boolean;
  acquisitionDate: string; // ISO date
  daysHeld: number;
}

/**
 * Analyze open tax lots for harvest opportunities (losses only).
 *
 * @param taxLots          - Array of open tax lots
 * @param currentPrices    - token symbol (upper) -> current USD price
 * @param recentPurchases  - token -> array of ISO date strings within last 30 days
 * @param shortTermRate    - Estimated marginal short-term tax rate
 * @param longTermRate     - Estimated marginal long-term tax rate
 * @param asOfDate         - Date to calculate from (default: today)
 * @returns                Suggestions sorted by potentialTaxSavings descending
 */
export function analyzeHarvest(
  taxLots: TaxLotInput[],
  currentPrices: Record<string, Decimal>,
  recentPurchases: Record<string, string[]> = {},
  shortTermRate: Decimal = SHORT_TERM_RATE,
  longTermRate: Decimal = LONG_TERM_RATE,
  asOfDate?: string,
): HarvestSuggestion[] {
  const today = asOfDate
    ? new Date(asOfDate.slice(0, 10) + 'T00:00:00Z')
    : new Date();

  const suggestions: HarvestSuggestion[] = [];

  for (const lot of taxLots) {
    if (lot.remaining.lte('0')) continue;

    const token = lot.token.toUpperCase();
    const currentPrice = currentPrices[token];
    if (currentPrice === undefined) continue;

    if (lot.amount.lte('0')) continue;

    const costPerUnit = lot.costBasisUsd.div(lot.amount);
    const currentValue = lot.remaining.times(currentPrice);
    const costOfRemaining = lot.remaining.times(costPerUnit);
    const unrealized = currentValue.minus(costOfRemaining);

    if (unrealized.gte('0')) continue; // skip gains

    let acqDate: Date;
    try {
      acqDate = new Date(lot.acquisitionDate.slice(0, 10) + 'T00:00:00Z');
      if (isNaN(acqDate.getTime())) continue;
    } catch {
      continue;
    }

    const daysHeld = Math.floor(
      (today.getTime() - acqDate.getTime()) / 86400000,
    );
    const holdingPeriod = daysHeld >= LONG_TERM_DAYS ? 'long' : 'short';

    const rate = holdingPeriod === 'long' ? longTermRate : shortTermRate;
    const potentialSavings = unrealized.abs().times(rate);

    // Wash sale: warn if same token purchased within 30 days
    const washWarning = checkWashSale(token, today, recentPurchases);

    suggestions.push({
      token,
      lotId: lot.id,
      amountRemaining: lot.remaining,
      costBasisPerUnit: costPerUnit,
      currentPriceUsd: currentPrice,
      unrealizedLossUsd: unrealized,
      holdingPeriod,
      potentialTaxSavings: potentialSavings,
      washSaleWarning: washWarning,
      acquisitionDate: lot.acquisitionDate.slice(0, 10),
      daysHeld,
    });
  }

  // Sort by potential savings descending
  suggestions.sort((a, b) =>
    b.potentialTaxSavings.cmp(a.potentialTaxSavings),
  );

  return suggestions;
}

/**
 * Wash sale warning: was this token purchased within 30 days before/after sell date?
 */
function checkWashSale(
  token: string,
  sellDate: Date,
  recentPurchases: Record<string, string[]>,
): boolean {
  const dates = recentPurchases[token] ?? [];
  for (const dateStr of dates) {
    try {
      const d = new Date(dateStr);
      const diffDays = Math.abs(
        Math.floor((d.getTime() - sellDate.getTime()) / 86400000),
      );
      if (diffDays <= 30) return true;
    } catch {
      // skip invalid dates
    }
  }
  return false;
}

/**
 * Generate a human-readable harvest report.
 */
export function formatHarvestReport(
  suggestions: HarvestSuggestion[],
  shortTermRate: Decimal = SHORT_TERM_RATE,
  longTermRate: Decimal = LONG_TERM_RATE,
): string {
  if (suggestions.length === 0) {
    return 'No tax loss harvesting opportunities found.';
  }

  const lines: string[] = [
    'Tax Loss Harvesting Suggestions',
    '='.repeat(60),
    `(Rates used: ST=${shortTermRate.times(100).toFixed(0)}%, LT=${longTermRate.times(100).toFixed(0)}%)`,
    '',
  ];

  for (let i = 0; i < suggestions.length; i++) {
    const s = suggestions[i];
    const wash = s.washSaleWarning ? ' !! WASH SALE RISK' : '';
    const amtStr = s.amountRemaining.toFixed(8).replace(/0+$/, '').replace(/\.$/, '');
    lines.push(
      `${i + 1}. ${s.token} -- ${s.holdingPeriod.charAt(0).toUpperCase() + s.holdingPeriod.slice(1)}-Term${wash}`,
      `   Lot acquired: ${s.acquisitionDate} (${s.daysHeld} days held)`,
      `   Amount:        ${amtStr} ${s.token}`,
      `   Cost basis/unit: $${s.costBasisPerUnit.toFixed(4)}`,
      `   Current price:   $${s.currentPriceUsd.toFixed(4)}`,
      `   Unrealized loss: $${s.unrealizedLossUsd.toFixed(2)}`,
      `   Potential savings: $${s.potentialTaxSavings.toFixed(2)}`,
      '',
    );
  }

  if (suggestions.some((s) => s.washSaleWarning)) {
    lines.push(
      '!!  WASH SALE WARNING: IRS has not definitively ruled on crypto wash sales.',
      '   Selling and rebuying the same asset within 30 days may disallow the loss.',
      '   Consult a tax professional before harvesting flagged positions.',
    );
  }

  return lines.join('\n');
}
