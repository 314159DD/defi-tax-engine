/**
 * Transaction CRUD operations on the Dexie database.
 */

import { db, type DBTransaction } from './index';

export interface TransactionFilters {
  chain?: string;
  txType?: string;
  year?: number;
  limit?: number;
  offset?: number;
}

/**
 * Bulk upsert (insert or replace) transactions.
 * Uses Dexie's bulkPut which performs upserts on the compound primary key.
 */
export async function bulkUpsertTransactions(
  txs: DBTransaction[],
): Promise<void> {
  await db.transactions.bulkPut(txs);
}

/**
 * Get transactions with optional filtering and pagination.
 */
export async function getTransactions(
  filters: TransactionFilters = {},
): Promise<DBTransaction[]> {
  let collection = db.transactions.orderBy('timestamp');

  if (filters.chain) {
    collection = db.transactions
      .where('chain')
      .equals(filters.chain.toLowerCase())
      .reverse(); // newest first by default when filtered
  }

  let results = await collection.toArray();

  // Apply additional filters in memory (Dexie compound filters are limited)
  if (filters.txType) {
    results = results.filter((tx) => tx.txType === filters.txType);
  }

  if (filters.year) {
    const yearStr = String(filters.year);
    results = results.filter((tx) => tx.timestamp.startsWith(yearStr));
  }

  // If we filtered by chain, re-sort by timestamp descending
  if (filters.chain) {
    results.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  }

  // Pagination
  const offset = filters.offset ?? 0;
  const limit = filters.limit ?? results.length;
  return results.slice(offset, offset + limit);
}

/**
 * Count transactions matching filters.
 */
export async function getTransactionCount(
  filters: Omit<TransactionFilters, 'limit' | 'offset'> = {},
): Promise<number> {
  if (!filters.chain && !filters.txType && !filters.year) {
    return db.transactions.count();
  }

  // For filtered counts, we must load and count in memory
  const all = await getTransactions({ ...filters, limit: undefined, offset: undefined });
  return all.length;
}

/**
 * Get a single transaction by hash and chain.
 */
export async function getTransaction(
  txHash: string,
  chain: string,
): Promise<DBTransaction | undefined> {
  return db.transactions.get([txHash, chain.toLowerCase()]);
}

/**
 * Get the latest transaction timestamp for a chain.
 * Returns null if no transactions exist for that chain.
 */
export async function getLatestTimestamp(
  chain: string,
): Promise<string | null> {
  const results = await db.transactions
    .where('chain')
    .equals(chain.toLowerCase())
    .reverse()
    .sortBy('timestamp');

  if (results.length === 0) return null;
  return results[0].timestamp;
}

/**
 * Clear all transactions.
 */
export async function clearTransactions(): Promise<void> {
  await db.transactions.clear();
}

/**
 * Clear transactions for a specific chain.
 */
export async function clearTransactionsByChain(chain: string): Promise<void> {
  await db.transactions.where('chain').equals(chain.toLowerCase()).delete();
}
