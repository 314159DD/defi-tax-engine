/**
 * Encrypted backup and restore for the entire client-side database.
 *
 * Export: Dumps all 6 tables to JSON, encrypts with AES-256-GCM, returns Blob.
 * Import: Decrypts Blob, validates structure, restores all tables.
 * Clear:  Wipes all tables.
 */

import { db } from './index';
import { encrypt, decrypt } from './crypto';

interface BackupPayload {
  version: 1;
  exportedAt: string;
  wallets: unknown[];
  transactions: unknown[];
  taxLots: unknown[];
  disposals: unknown[];
  priceCache: unknown[];
  settings: unknown[];
}

/**
 * Export the entire database as an encrypted Blob.
 *
 * @param encryptionKey - AES-256-GCM CryptoKey from deriveKey()
 * @returns Encrypted Blob containing all database tables
 */
export async function exportBackup(encryptionKey: CryptoKey): Promise<Blob> {
  const payload: BackupPayload = {
    version: 1,
    exportedAt: new Date().toISOString(),
    wallets: await db.wallets.toArray(),
    transactions: await db.transactions.toArray(),
    taxLots: await db.taxLots.toArray(),
    disposals: await db.disposals.toArray(),
    priceCache: await db.priceCache.toArray(),
    settings: await db.settings.toArray(),
  };

  const json = JSON.stringify(payload);
  const encrypted = await encrypt(json, encryptionKey);

  return new Blob([encrypted], { type: 'application/octet-stream' });
}

/**
 * Import a backup from an encrypted Blob.
 *
 * Decrypts and validates the payload, then replaces all tables.
 * This is a destructive operation - existing data is wiped first.
 *
 * @param blob - Encrypted Blob from exportBackup()
 * @param encryptionKey - AES-256-GCM CryptoKey (same userId + salt as export)
 */
export async function importBackup(
  blob: Blob,
  encryptionKey: CryptoKey,
): Promise<void> {
  const arrayBuffer = await blob.arrayBuffer();
  const json = await decrypt(arrayBuffer, encryptionKey);

  const payload = JSON.parse(json) as BackupPayload;

  // Validate structure
  if (payload.version !== 1) {
    throw new Error(`Unsupported backup version: ${payload.version}`);
  }
  if (!Array.isArray(payload.wallets)) {
    throw new Error('Invalid backup: missing wallets array');
  }
  if (!Array.isArray(payload.transactions)) {
    throw new Error('Invalid backup: missing transactions array');
  }

  // Restore all tables in a single transaction
  await db.transaction(
    'rw',
    [db.wallets, db.transactions, db.taxLots, db.disposals, db.priceCache, db.settings],
    async () => {
      // Clear all existing data
      await db.wallets.clear();
      await db.transactions.clear();
      await db.taxLots.clear();
      await db.disposals.clear();
      await db.priceCache.clear();
      await db.settings.clear();

      // Restore from backup
      if (payload.wallets.length > 0) {
        await db.wallets.bulkPut(payload.wallets as Parameters<typeof db.wallets.bulkPut>[0]);
      }
      if (payload.transactions.length > 0) {
        await db.transactions.bulkPut(payload.transactions as Parameters<typeof db.transactions.bulkPut>[0]);
      }
      if (payload.taxLots.length > 0) {
        await db.taxLots.bulkPut(payload.taxLots as Parameters<typeof db.taxLots.bulkPut>[0]);
      }
      if (payload.disposals.length > 0) {
        await db.disposals.bulkPut(payload.disposals as Parameters<typeof db.disposals.bulkPut>[0]);
      }
      if (payload.priceCache.length > 0) {
        await db.priceCache.bulkPut(payload.priceCache as Parameters<typeof db.priceCache.bulkPut>[0]);
      }
      if (payload.settings.length > 0) {
        await db.settings.bulkPut(payload.settings as Parameters<typeof db.settings.bulkPut>[0]);
      }
    },
  );
}

/**
 * Clear all data from every table.
 */
export async function clearAllData(): Promise<void> {
  await db.transaction(
    'rw',
    [db.wallets, db.transactions, db.taxLots, db.disposals, db.priceCache, db.settings],
    async () => {
      await db.wallets.clear();
      await db.transactions.clear();
      await db.taxLots.clear();
      await db.disposals.clear();
      await db.priceCache.clear();
      await db.settings.clear();
    },
  );
}

/**
 * Get a summary of what's in the database (for UI display).
 */
export async function getDatabaseSummary(): Promise<{
  walletCount: number;
  transactionCount: number;
  taxLotCount: number;
  disposalCount: number;
  priceCacheCount: number;
}> {
  return {
    walletCount: await db.wallets.count(),
    transactionCount: await db.transactions.count(),
    taxLotCount: await db.taxLots.count(),
    disposalCount: await db.disposals.count(),
    priceCacheCount: await db.priceCache.count(),
  };
}
