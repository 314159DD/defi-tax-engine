/**
 * DEX swap detection rule.
 *
 * A swap exchanges token A for token B via a DEX. It IS a taxable event:
 * - The tokens sent out are a disposal (potential capital gain/loss)
 * - The tokens received set the acquisition cost basis
 *
 * Ported from: src/categorizer/rules/swap.py
 */

import type { Transaction } from '../../types';
import { DEX_ADDRESSES, resolveProtocol } from '../protocols';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

// Known wrapped token symbol pairs -- wrapping is NOT taxable
const WRAP_SYMBOL_PAIRS: ReadonlySet<string> = new Set([
  'ETH:WETH',
  'WETH:ETH',
  'BTC:WBTC',
  'WBTC:BTC',
  'MATIC:WMATIC',
  'WMATIC:MATIC',
  'BNB:WBNB',
  'WBNB:BNB',
]);

function isWrap(tx: Transaction): boolean {
  if (tx.assetsIn.length === 1 && tx.assetsOut.length === 1) {
    const pair = `${tx.assetsOut[0].tokenSymbol.toUpperCase()}:${tx.assetsIn[0].tokenSymbol.toUpperCase()}`;
    return WRAP_SYMBOL_PAIRS.has(pair);
  }
  return false;
}

const DEX_PROTOCOL_KEYWORDS = [
  'uniswap', 'sushiswap', 'curve', 'balancer', '1inch', 'paraswap',
  'pancakeswap', 'quickswap', 'trader joe', 'raydium', 'orca', 'jupiter',
];

/**
 * Return true if this transaction is a DEX swap.
 *
 * Conditions:
 * - Has both assetsIn and assetsOut
 * - toAddress is a known DEX router, OR protocol is a known DEX
 * - NOT a wrap (ETH->WETH etc.)
 */
export function isSwap(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;

  const toAddr = tx.toAddress.toLowerCase();
  if (DEX_ADDRESSES.has(toAddr)) {
    return !isWrap(tx);
  }

  // Protocol already resolved (e.g. from Solana parser)
  if (
    tx.protocol &&
    DEX_PROTOCOL_KEYWORDS.some((kw) => tx.protocol!.toLowerCase().includes(kw))
  ) {
    return !isWrap(tx);
  }

  return false;
}

/**
 * If this is a DEX swap, set txType to 'swap' and return updated tx.
 * Returns null if rule does not apply.
 */
export function apply(tx: Transaction, _context: CategorizerContext): Transaction | null {
  if (!isSwap(tx)) return null;

  const protocol = tx.protocol || resolveProtocol(tx.toAddress) || 'DEX';

  return {
    ...tx,
    txType: 'swap',
    protocol,
  };
}
