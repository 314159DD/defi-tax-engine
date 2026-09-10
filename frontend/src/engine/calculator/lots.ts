/**
 * LotManager - in-memory tax lot book.
 *
 * Manages a per-token collection of open TaxLots. Used by the calculator
 * engine as it walks transactions in chronological order.
 *
 * Ported from: src/calculator/lots.py
 *
 * CRITICAL: All arithmetic uses Decimal methods - NEVER native JS operators on money.
 */

import Decimal from 'decimal.js';
import type { TaxLot, LotConsumption } from '../types';
import { consumeFifo } from './fifo';
import { consumeLifo } from './lifo';
import { consumeHifo } from './hifo';

/** Lots with remaining below this are considered fully consumed. */
const EPSILON = new Decimal('0.00000001');

export type CostBasisMethod = 'FIFO' | 'LIFO' | 'HIFO';

/**
 * In-memory lot book keyed by token symbol.
 *
 * Mutations happen in-place on TaxLot.remaining during consumption.
 */
export class LotManager {
  private _lots: Map<string, TaxLot[]> = new Map();

  // ── Acquisition ─────────────────────────────────────────────────────

  /** Add a new acquisition lot for the given token. */
  addLot(lot: TaxLot): void {
    const existing = this._lots.get(lot.token);
    if (existing) {
      existing.push(lot);
    } else {
      this._lots.set(lot.token, [lot]);
    }
  }

  // ── Query ───────────────────────────────────────────────────────────

  /** Return lots with remaining > EPSILON in insertion order. */
  getOpenLots(token: string): TaxLot[] {
    const lots = this._lots.get(token) ?? [];
    return lots.filter((lot) => lot.remaining.greaterThan(EPSILON));
  }

  /** Sum of remaining cost basis across all open lots for a token. */
  totalBasis(token: string): Decimal {
    return this.getOpenLots(token).reduce((sum, lot) => {
      const costPerUnit = lot.amount.isZero()
        ? new Decimal('0')
        : lot.costBasisUsd.dividedBy(lot.amount);
      return sum.plus(lot.remaining.times(costPerUnit));
    }, new Decimal('0'));
  }

  /** Sum of remaining units across all open lots for a token. */
  totalRemaining(token: string): Decimal {
    return this.getOpenLots(token).reduce(
      (sum, lot) => sum.plus(lot.remaining),
      new Decimal('0'),
    );
  }

  // ── Consumption ─────────────────────────────────────────────────────

  /**
   * Consume `amount` of `token` using the specified cost basis method.
   *
   * Delegates to the correct sorting strategy (FIFO/LIFO/HIFO), then
   * returns the LotConsumption records describing what was used.
   *
   * Lots are MUTATED in-place (remaining decremented).
   *
   * @throws Error if insufficient lots exist for this token.
   */
  consumeLots(
    token: string,
    amount: Decimal,
    method: CostBasisMethod,
  ): LotConsumption[] {
    const openLots = this.getOpenLots(token);
    if (openLots.length === 0) {
      throw new Error(`No open lots for token '${token}'`);
    }

    switch (method) {
      case 'FIFO':
        return consumeFifo(openLots, amount);
      case 'LIFO':
        return consumeLifo(openLots, amount);
      case 'HIFO':
        return consumeHifo(openLots, amount);
      default:
        throw new Error(`Unknown cost basis method: '${method as string}'`);
    }
  }

  /** Get a snapshot of all lots (open and consumed) for all tokens. */
  getAllLots(): TaxLot[] {
    const result: TaxLot[] = [];
    for (const lots of this._lots.values()) {
      result.push(...lots);
    }
    return result;
  }
}

// ---------------------------------------------------------------------------
// Holding period helper
// ---------------------------------------------------------------------------

const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000;

/**
 * Return 'long-term' if held > 1 year (365 days), else 'short-term'.
 *
 * Both dates are ISO strings. Comparison is by millisecond difference.
 */
export function holdingPeriod(
  acquisitionDate: string,
  disposalDate: string,
): 'short-term' | 'long-term' {
  const acq = new Date(acquisitionDate).getTime();
  const disp = new Date(disposalDate).getTime();
  return (disp - acq) > ONE_YEAR_MS ? 'long-term' : 'short-term';
}

/**
 * Determine dominant holding period for a blended disposal.
 *
 * If >= 50% of consumed amount (by units) is long-term, returns 'long-term'.
 * Otherwise returns 'short-term'.
 */
export function blendedHoldingPeriod(
  consumptions: LotConsumption[],
  disposalDate: string,
  totalAmount: Decimal,
): string {
  if (consumptions.length === 0 || totalAmount.isZero()) {
    return 'short-term';
  }

  let longTermAmount = new Decimal('0');
  for (const c of consumptions) {
    const hp = holdingPeriod(c.acquisitionDate, disposalDate);
    if (hp === 'long-term') {
      longTermAmount = longTermAmount.plus(c.amountConsumed);
    }
  }

  if (longTermAmount.dividedBy(totalAmount).greaterThanOrEqualTo(new Decimal('0.5'))) {
    return 'long-term';
  }
  return 'short-term';
}
