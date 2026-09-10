/**
 * Disposal CRUD operations on the Dexie database.
 */

import { db, type DBDisposal } from './index';

/**
 * Save a batch of disposals for a given method, year, and country.
 * Replaces existing disposals matching that combination.
 */
export async function saveDisposals(
  disposals: DBDisposal[],
  method: string,
  year: number,
  country: string,
): Promise<void> {
  const upperMethod = method.toUpperCase();
  const upperCountry = country.toUpperCase();

  await db.transaction('rw', db.disposals, async () => {
    // Clear existing disposals for this method+year+country
    await db.disposals
      .where('[method+year+country]')
      .equals([upperMethod, year, upperCountry])
      .delete();

    // Insert new disposals
    await db.disposals.bulkPut(
      disposals.map((d) => ({
        ...d,
        method: upperMethod,
        year,
        country: upperCountry,
      })),
    );
  });
}

/**
 * Get disposals for a given method, year, and country.
 * Sorted by disposal date ascending.
 */
export async function getDisposals(
  method: string,
  year: number,
  country: string,
): Promise<DBDisposal[]> {
  const results = await db.disposals
    .where('[method+year+country]')
    .equals([method.toUpperCase(), year, country.toUpperCase()])
    .toArray();

  return results.sort((a, b) => a.disposalDate.localeCompare(b.disposalDate));
}

/**
 * Get all disposals for a given method (across all years/countries).
 */
export async function getDisposalsByMethod(
  method: string,
): Promise<DBDisposal[]> {
  return db.disposals
    .where('method')
    .equals(method.toUpperCase())
    .sortBy('disposalDate');
}

/**
 * Get all disposals for a given year (across all methods/countries).
 */
export async function getDisposalsByYear(year: number): Promise<DBDisposal[]> {
  return db.disposals
    .where('year')
    .equals(year)
    .sortBy('disposalDate');
}

/**
 * Get a single disposal by id.
 */
export async function getDisposal(
  id: string,
): Promise<DBDisposal | undefined> {
  return db.disposals.get(id);
}

/**
 * Clear all disposals for a given method.
 */
export async function clearDisposals(method: string): Promise<void> {
  await db.disposals.where('method').equals(method.toUpperCase()).delete();
}

/**
 * Clear all disposals.
 */
export async function clearAllDisposals(): Promise<void> {
  await db.disposals.clear();
}
