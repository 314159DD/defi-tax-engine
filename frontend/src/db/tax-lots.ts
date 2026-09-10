/**
 * TaxLot CRUD operations on the Dexie database.
 */

import { db, type DBTaxLot } from './index';

/**
 * Save a batch of tax lots for a given calculation method.
 * Replaces existing lots for that method.
 */
export async function saveLots(
  lots: DBTaxLot[],
  method: string,
): Promise<void> {
  await db.transaction('rw', db.taxLots, async () => {
    // Clear existing lots for this method first
    await db.taxLots.where('method').equals(method.toUpperCase()).delete();
    // Insert new lots
    await db.taxLots.bulkPut(
      lots.map((lot) => ({ ...lot, method: method.toUpperCase() })),
    );
  });
}

/**
 * Get all tax lots for a given calculation method.
 */
export async function getLots(method: string): Promise<DBTaxLot[]> {
  return db.taxLots
    .where('method')
    .equals(method.toUpperCase())
    .sortBy('acquisitionDate');
}

/**
 * Get open lots (remaining > 0) for a token and method.
 */
export async function getOpenLots(
  token: string,
  method: string,
): Promise<DBTaxLot[]> {
  const lots = await db.taxLots
    .where('[token+method]')
    .equals([token, method.toUpperCase()])
    .toArray();

  // Filter remaining > 0 in memory (stored as string)
  return lots.filter((lot) => {
    const remaining = parseFloat(lot.remaining);
    return remaining > 0;
  });
}

/**
 * Get a single lot by id.
 */
export async function getLot(id: string): Promise<DBTaxLot | undefined> {
  return db.taxLots.get(id);
}

/**
 * Update the remaining amount of a lot.
 */
export async function updateLotRemaining(
  id: string,
  remaining: string,
): Promise<void> {
  await db.taxLots.update(id, { remaining });
}

/**
 * Clear all lots for a given method.
 */
export async function clearLots(method: string): Promise<void> {
  await db.taxLots.where('method').equals(method.toUpperCase()).delete();
}

/**
 * Clear all lots.
 */
export async function clearAllLots(): Promise<void> {
  await db.taxLots.clear();
}
