/**
 * Self-transfer detection rule.
 *
 * A self-transfer is a transaction where both the from and to addresses belong
 * to the user's known wallets. It is NOT a taxable event -- the cost basis
 * carries over to the destination wallet.
 *
 * Ported from: src/categorizer/rules/transfer.py
 */

import type { Transaction } from '../../types';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

/**
 * Return true if this transaction is a self-transfer between user wallets.
 */
export function isSelfTransfer(tx: Transaction, knownWallets: ReadonlySet<string>): boolean {
  return (
    knownWallets.has(tx.fromAddress.toLowerCase()) &&
    knownWallets.has(tx.toAddress.toLowerCase())
  );
}

/**
 * If this is a self-transfer, set txType to 'transfer' and return updated tx.
 * Returns null if rule does not apply.
 */
export function apply(tx: Transaction, context: CategorizerContext): Transaction | null {
  if (isSelfTransfer(tx, context.knownWallets)) {
    return {
      ...tx,
      txType: 'transfer',
    };
  }
  return null;
}
