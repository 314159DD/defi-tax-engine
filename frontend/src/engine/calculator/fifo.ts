/**
 * FIFO (First In, First Out) lot consumption.
 *
 * Consumes the oldest acquisition lots first (sorted by acquisitionDate ascending).
 * Generally results in more long-term gains (lower tax rate) for assets
 * that have appreciated over time.
 *
 * Ported from: src/calculator/fifo.py
 */

import Decimal from 'decimal.js';
import type { TaxLot, LotConsumption } from '../types';

/**
 * Consume `amount` of a token using FIFO order.
 *
 * Oldest lots are consumed first (smallest acquisitionDate first).
 * Lots are MUTATED in-place: `lot.remaining` is decreased.
 *
 * @param lots   Open lots for the token (remaining > 0). Will be sorted internally.
 * @param amount Units to consume.
 * @returns Array of LotConsumption records describing which lots were used.
 * @throws Error if insufficient lots exist.
 */
export function consumeFifo(
  lots: TaxLot[],
  amount: Decimal,
): LotConsumption[] {
  const EPSILON = new Decimal('0.00000001');

  // Sort oldest first (ascending acquisitionDate). Stable sort preserves insertion order for ties.
  const sorted = [...lots].sort((a, b) => {
    if (a.acquisitionDate < b.acquisitionDate) return -1;
    if (a.acquisitionDate > b.acquisitionDate) return 1;
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
