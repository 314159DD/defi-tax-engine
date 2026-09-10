/**
 * Tax loss harvesting simulation engine.
 *
 * Ported from src/reports/harvest_simulator.py.
 *
 * Allows users to select positions for hypothetical sale and see the projected
 * tax impact before committing. Supports multi-position scenarios and
 * country-specific rules (US wash sales, DE Freigrenze cliff).
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import { HoldingPeriod } from '../types';
import type { UnrealizedPosition } from './harvest';

// German Freigrenze (EUR 1,000 cliff -- §23 Abs. 3 Satz 5 EStG)
const DE_FREIGRENZE = new Decimal('1000');

// ---------------------------------------------------------------------------
// HarvestScenario
// ---------------------------------------------------------------------------

export interface HarvestScenario {
  positionsToSell: string[];           // lot IDs
  totalRealizedLoss: Decimal;
  totalRealizedGain: Decimal;
  netImpact: Decimal;                  // gain - loss
  projectedTaxSavings: Decimal;
  // DE-specific Freigrenze impact
  freigrenzeImpact: string;            // "stays_under" | "would_exceed" | "already_exceeded" | "n/a"
  newFreigrenzeTotal: Decimal;         // new YTD short-term gains after harvest
}

/**
 * Simulate selling selected positions and calculate tax impact.
 *
 * @param positions         - Array of UnrealizedPosition objects
 * @param country           - "US" or "DE"
 * @param currentYearGains  - Total realized short-term gains YTD (for Freigrenze check)
 * @param userBracket       - User's estimated marginal tax rate (e.g. Decimal("0.37"))
 * @param selectedLotIds    - Lot IDs to sell. If null/undefined, sell all.
 * @returns HarvestScenario with projected impact
 */
export function simulateHarvest(
  positions: UnrealizedPosition[],
  country: string,
  currentYearGains: Decimal,
  userBracket: Decimal,
  selectedLotIds?: string[] | null,
): HarvestScenario {
  // Filter to selected positions
  let selected: UnrealizedPosition[];
  if (selectedLotIds != null) {
    const selectedSet = new Set(selectedLotIds);
    selected = positions.filter((p) => selectedSet.has(p.lotId));
  } else {
    selected = [...positions];
  }

  if (selected.length === 0) {
    return {
      positionsToSell: [],
      totalRealizedLoss: new Decimal('0'),
      totalRealizedGain: new Decimal('0'),
      netImpact: new Decimal('0'),
      projectedTaxSavings: new Decimal('0'),
      freigrenzeImpact: 'n/a',
      newFreigrenzeTotal: currentYearGains,
    };
  }

  let totalLoss = new Decimal('0');
  let totalGain = new Decimal('0');
  const lotIds: string[] = [];

  // Track short-term gains/losses separately for Freigrenze
  let shortTermGainDelta = new Decimal('0');

  for (const pos of selected) {
    lotIds.push(pos.lotId);
    const gl = pos.unrealizedGainLoss;

    if (gl.lt('0')) {
      totalLoss = totalLoss.plus(gl.abs());
    } else {
      totalGain = totalGain.plus(gl);
    }

    // For DE Freigrenze: only short-term disposals count
    if (country === 'DE' && pos.holdingPeriod === HoldingPeriod.SHORT_TERM) {
      shortTermGainDelta = shortTermGainDelta.plus(gl);
    }
  }

  const netImpact = totalGain.minus(totalLoss);

  // Calculate projected tax savings
  let projectedSavings: Decimal;
  if (netImpact.lt('0')) {
    // Net loss -> savings
    projectedSavings = netImpact.abs().times(userBracket).toDecimalPlaces(2);
  } else {
    // Net gain -> negative savings (additional tax)
    projectedSavings = netImpact.times(userBracket).neg().toDecimalPlaces(2);
  }

  // DE-specific: Freigrenze analysis
  let freigrenzeImpact = 'n/a';
  let newFreigrenzeTotal = currentYearGains;

  if (country === 'DE') {
    newFreigrenzeTotal = currentYearGains.plus(shortTermGainDelta);

    if (currentYearGains.gte(DE_FREIGRENZE)) {
      freigrenzeImpact = 'already_exceeded';
    } else if (newFreigrenzeTotal.gte(DE_FREIGRENZE)) {
      freigrenzeImpact = 'would_exceed';
    } else {
      freigrenzeImpact = 'stays_under';
    }
  }

  return {
    positionsToSell: lotIds,
    totalRealizedLoss: totalLoss,
    totalRealizedGain: totalGain,
    netImpact,
    projectedTaxSavings: projectedSavings,
    freigrenzeImpact,
    newFreigrenzeTotal,
  };
}

/**
 * Calculate how much more the user can harvest before hitting the Freigrenze cliff.
 *
 * @param currentYearGains - Total realized short-term gains YTD
 * @returns Freigrenze headroom info
 */
export function getFreigrenzeHeadroom(
  currentYearGains: Decimal,
): {
  limit: string;
  realizedYtd: string;
  remaining: string;
  status: 'under' | 'at_limit' | 'over';
} {
  const remaining = Decimal.max(DE_FREIGRENZE.minus(currentYearGains), '0');

  let status: 'under' | 'at_limit' | 'over';
  if (currentYearGains.gte(DE_FREIGRENZE)) {
    status = 'over';
  } else if (remaining.isZero()) {
    status = 'at_limit';
  } else {
    status = 'under';
  }

  return {
    limit: DE_FREIGRENZE.toString(),
    realizedYtd: currentYearGains.toString(),
    remaining: remaining.toString(),
    status,
  };
}
