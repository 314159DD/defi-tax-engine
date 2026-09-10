/**
 * Bridge transaction detection rule.
 *
 * A bridge moves assets cross-chain. It is NOT a taxable event -- the cost basis
 * carries over to the destination chain.
 *
 * Enhanced detection:
 * - Expanded bridge protocol list: Across, Stargate, Hop, Synapse, Orbiter, Wormhole
 * - Cross-chain matching: same token, amount within 2% tolerance, timing within 30min
 * - Bridge fee = deductible expense (added to cost basis of received tokens)
 *
 * Ported from: src/categorizer/rules/bridge.py
 */

import Decimal from 'decimal.js';
import type { Transaction } from '../../types';
import { BRIDGE_ADDRESSES, resolveProtocol } from '../protocols';
import { isEquivalent } from '../token-pairs';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

// -- Bridge matching tolerance --
const AMOUNT_TOLERANCE = new Decimal('0.02'); // 2% tolerance for bridge fees
const TIME_TOLERANCE_MS = 30 * 60 * 1000; // 30 minutes in milliseconds

/**
 * Return true if this transaction interacts with a known bridge contract.
 */
export function isBridge(tx: Transaction): boolean {
  const toAddr = tx.toAddress.toLowerCase();
  const fromAddr = tx.fromAddress.toLowerCase();

  if (BRIDGE_ADDRESSES.has(toAddr)) return true;
  if (BRIDGE_ADDRESSES.has(fromAddr)) return true;

  // Check protocol name already set
  if (
    tx.protocol &&
    ['bridge', 'hop', 'stargate', 'across', 'synapse', 'celer',
     'multichain', 'orbiter', 'wormhole', 'layerzero'].some(
      (kw) => tx.protocol!.toLowerCase().includes(kw),
    )
  ) {
    return true;
  }

  // Check rawData for bridge-related function names
  const method = (tx.rawData.functionName as string) ?? (tx.rawData.method as string) ?? '';
  if (
    typeof method === 'string' &&
    ['deposit', 'bridge', 'relay', 'sendmessage', 'fillrelay'].some(
      (kw) => method.toLowerCase().includes(kw),
    )
  ) {
    if (BRIDGE_ADDRESSES.has(toAddr) || BRIDGE_ADDRESSES.has(fromAddr)) {
      return true;
    }
  }

  return false;
}

/**
 * Determine if two transactions form a bridge pair (source chain -> dest chain).
 *
 * Matching criteria:
 * 1. Different chains
 * 2. Same token (or canonical equivalent, e.g. USDC.e <-> USDC)
 * 3. Amount within 2% tolerance (bridge takes a fee)
 * 4. Timing within 30 minutes
 */
export function matchBridgePair(sourceTx: Transaction, destTx: Transaction): boolean {
  // Must be on different chains
  if (sourceTx.chain === destTx.chain) return false;

  // Must have outgoing on source and incoming on destination
  if (sourceTx.assetsOut.length === 0 || destTx.assetsIn.length === 0) return false;

  // Check timing
  const timeDiff = Math.abs(
    new Date(destTx.timestamp).getTime() - new Date(sourceTx.timestamp).getTime(),
  );
  if (timeDiff > TIME_TOLERANCE_MS) return false;

  // Check token equivalence and amount tolerance
  for (const outAsset of sourceTx.assetsOut) {
    for (const inAsset of destTx.assetsIn) {
      if (isEquivalent(outAsset.tokenSymbol, inAsset.tokenSymbol)) {
        if (outAsset.amount.gt(0) && inAsset.amount.gt(0)) {
          const ratio = outAsset.amount.sub(inAsset.amount).abs().div(outAsset.amount);
          if (ratio.lte(AMOUNT_TOLERANCE)) {
            return true;
          }
        }
      }
    }
  }

  return false;
}

/**
 * Calculate the bridge fee as the difference between sent and received amounts.
 * Returns Decimal("0") if amounts cannot be compared.
 */
export function calculateBridgeFee(sourceTx: Transaction, destTx: Transaction): Decimal {
  if (sourceTx.assetsOut.length === 0 || destTx.assetsIn.length === 0) {
    return new Decimal(0);
  }

  for (const outAsset of sourceTx.assetsOut) {
    for (const inAsset of destTx.assetsIn) {
      if (isEquivalent(outAsset.tokenSymbol, inAsset.tokenSymbol)) {
        const fee = outAsset.amount.sub(inAsset.amount);
        return Decimal.max(fee, new Decimal(0));
      }
    }
  }

  return new Decimal(0);
}

/**
 * If this is a bridge transaction, set txType to 'bridge' and return updated tx.
 * Returns null if rule does not apply.
 */
export function apply(tx: Transaction, _context: CategorizerContext): Transaction | null {
  if (!isBridge(tx)) return null;

  const protocol =
    tx.protocol ||
    resolveProtocol(tx.toAddress) ||
    resolveProtocol(tx.fromAddress) ||
    'Bridge';

  return {
    ...tx,
    txType: 'bridge',
    protocol,
  };
}
