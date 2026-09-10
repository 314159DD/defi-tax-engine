/**
 * Wallet CRUD operations on the Dexie database.
 */

import { db, type DBWallet } from './index';

/**
 * Add a new wallet. Returns the wallet id.
 */
export async function addWallet(wallet: {
  id: string;
  address: string;
  chain: string;
  label?: string | null;
}): Promise<string> {
  const row: DBWallet = {
    id: wallet.id,
    address: wallet.address.toLowerCase(),
    chain: wallet.chain.toLowerCase(),
    label: wallet.label ?? null,
    lastImportedAt: null,
  };
  await db.wallets.put(row);
  return wallet.id;
}

/**
 * Get all wallets.
 */
export async function getWallets(): Promise<DBWallet[]> {
  return db.wallets.toArray();
}

/**
 * Get a single wallet by id.
 */
export async function getWallet(id: string): Promise<DBWallet | undefined> {
  return db.wallets.get(id);
}

/**
 * Get all wallet addresses (lowercased).
 */
export async function getWalletAddresses(): Promise<string[]> {
  const wallets = await db.wallets.toArray();
  return wallets.map((w) => w.address);
}

/**
 * Delete a wallet by id.
 */
export async function deleteWallet(id: string): Promise<void> {
  await db.wallets.delete(id);
}

/**
 * Update the last imported timestamp for a wallet.
 */
export async function updateLastImported(
  id: string,
  timestamp: string,
): Promise<void> {
  await db.wallets.update(id, { lastImportedAt: timestamp });
}

/**
 * Update a wallet's label.
 */
export async function updateWalletLabel(
  id: string,
  label: string | null,
): Promise<void> {
  await db.wallets.update(id, { label });
}

/**
 * Check if a wallet address + chain combination already exists.
 */
export async function walletExists(
  address: string,
  chain: string,
): Promise<boolean> {
  const count = await db.wallets
    .where('[address+chain]')
    .equals([address.toLowerCase(), chain.toLowerCase()])
    .count();
  return count > 0;
}
