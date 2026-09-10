/**
 * HIFO (Highest In, First Out) lot consumption.
 *
 * Consumes lots with the highest cost-per-unit first (sorted by costPerUnit descending).
 * This minimizes taxable gain (or maximizes deductible loss) and is generally the
 * most tax-efficient method for appreciating assets.
 *
 * Ported from: src/calculator/hifo.py
 */

import Decimal from 'decimal.js';
import type { TaxLot, LotConsumption } from '../types';

/**
 * Consume `amount` of a token using HIFO order.
 *
 * Lots with the highest cost-per-unit are consumed first.
 * Lots are MUTATED in-place: `lot.remaining` is decreased.
 *
 * @param lots   Open lots for the token (remaining > 0). Will be sorted internally.
 * @param amount Units to consume.
 * @returns Array of LotConsumption records describing which lots were used.
 * @throws Error if insufficient lots exist.
 */
export function consumeHifo(
  lots: TaxLot[],
  amount: Decimal,
): LotConsumption[] {
  const EPSILON = new Decimal('0.00000001');

  // Sort by cost-per-unit descending (highest first).
  const sorted = [...lots].sort((a, b) => {
    const cpuA = a.amount.isZero()
      ? new Decimal('0')
      : a.costBasisUsd.dividedBy(a.amount);
    const cpuB = b.amount.isZero()
      ? new Decimal('0')
      : b.costBasisUsd.dividedBy(b.amount);
    // descending: b - a
    if (cpuB.greaterThan(cpuA)) return 1;
    if (cpuB.lessThan(cpuA)) return -1;
    return 0;
  });

  const consumptions: LotConsumption[] = [];
  let remainingToConsume = amount;

  for (const lot of sorted) {
    if (remainingToConsume.lessThanOrEqualTo(new Decimal('0'))) break;

    const costPerUnit = lot.amount.isZero()
      ? new Decimal('0')
      : lot.costBasisUsd.dividedBy(lot.amount);

    const toTake = Decimal.min(lot.remaining, remainingToConsume);
    const costTaken = toTake.times(costPerUnit);

    // Mutate lot in place
    lot.remaining = lot.remaining.minus(toTake);
    remainingToConsume = remainingToConsume.minus(toTake);

    consumptions.push({
      lotId: lot.id,
      token: lot.token,
      amountConsumed: toTake,
      costBasisConsumed: costTaken,
      acquisitionDate: lot.acquisitionDate,
    });
  }

  if (remainingToConsume.greaterThan(EPSILON)) {
    throw new Error(
      `Insufficient lots for ${lots[0]?.token ?? 'unknown'}: needed ${amount.toString()}, ` +
      `short by ${remainingToConsume.toString()}`
    );
  }

  return consumptions;
}
