/**
 * Price cache CRUD operations on the Dexie database.
 *
 * Caches historical USD prices by token + date (YYYY-MM-DD).
 * Same token + same date = same price. Cache aggressively.
 */

import { db, type DBPriceCache } from './index';

/**
 * Get the cached USD price for a token on a specific date.
 * Returns null if not cached.
 */
export async function getPrice(
  token: string,
  date: string,
): Promise<string | null> {
  const entry = await db.priceCache.get([token.toLowerCase(), date]);
  return entry?.usdPrice ?? null;
}

/**
 * Set (upsert) a cached price for a token on a specific date.
 */
export async function setPrice(
  token: string,
  date: string,
  usdPrice: string,
  source: string = 'coingecko',
): Promise<void> {
  await db.priceCache.put({
    token: token.toLowerCase(),
    date,
    usdPrice,
    source,
  });
}

/**
 * Batch set prices. Efficient for bulk imports.
 */
export async function batchSetPrices(
  entries: Array<{
    token: string;
    date: string;
    usdPrice: string;
    source?: string;
  }>,
): Promise<void> {
  const rows: DBPriceCache[] = entries.map((e) => ({
    token: e.token.toLowerCase(),
    date: e.date,
    usdPrice: e.usdPrice,
    source: e.source ?? 'coingecko',
  }));
  await db.priceCache.bulkPut(rows);
}

/**
 * Check if a price is cached for a token + date.
 */
export async function hasPrice(token: string, date: string): Promise<boolean> {
  const entry = await db.priceCache.get([token.toLowerCase(), date]);
  return entry !== undefined;
}

/**
 * Get all cached prices for a token.
 */
export async function getPricesForToken(
  token: string,
): Promise<DBPriceCache[]> {
  return db.priceCache
    .where('token')
    .equals(token.toLowerCase())
    .sortBy('date');
}

/**
 * Clear all cached prices.
 */
export async function clearPriceCache(): Promise<void> {
  await db.priceCache.clear();
}

/**
 * Get total number of cached prices.
 */
export async function getPriceCacheCount(): Promise<number> {
  return db.priceCache.count();
}
