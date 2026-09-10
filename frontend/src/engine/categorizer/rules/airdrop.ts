/**
 * Airdrop detection rule.
 *
 * An airdrop is tokens received with no corresponding outgoing assets.
 * It IS income -- taxed as ordinary income at FMV on the date of receipt.
 *
 * Also handles token distributions: governance rewards, protocol incentives, etc.
 *
 * Ported from: src/categorizer/rules/airdrop.py
 */

import type { Transaction } from '../../types';
import { STAKING_ADDRESSES } from '../protocols';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

/**
 * Return true if this transaction looks like an airdrop.
 *
 * Conditions:
 * 1. Assets received (assetsIn non-empty)
 * 2. No assets sent (assetsOut empty)
 * 3. NOT from a staking contract (handled by staking rule)
 * 4. Sender is NOT a user wallet (not a self-transfer)
 */
export function isAirdrop(tx: Transaction, knownWallets: ReadonlySet<string>): boolean {
  if (tx.assetsIn.length === 0) return false;
  if (tx.assetsOut.length > 0) return false;

  // If sender is a user wallet, this is a self-transfer not an airdrop
  if (knownWallets.has(tx.fromAddress.toLowerCase())) return false;

  // If sent from a staking contract, let staking rule handle it
  if (STAKING_ADDRESSES.has(tx.fromAddress.toLowerCase())) return false;

  return true;
}

/**
 * If this is an airdrop, set txType to 'airdrop' and return updated tx.
 * Returns null if rule does not apply.
 */
export function apply(tx: Transaction, context: CategorizerContext): Transaction | null {
  if (!isAirdrop(tx, context.knownWallets)) return null;

  return {
    ...tx,
    txType: 'airdrop',
  };
}
