/**
 * LP (liquidity position) add/remove detection rule.
 *
 * LP add: user sends two tokens to an AMM pool and receives LP tokens.
 * LP remove: user burns LP tokens and receives two tokens back.
 *
 * Tax treatment:
 * - LP add: NOT immediately taxable.
 * - LP remove: IS a taxable event.
 *
 * Ported from: src/categorizer/rules/liquidity.py
 */

import type { AssetTransfer, Transaction } from '../../types';
import { DEX_ADDRESSES, resolveProtocol } from '../protocols';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

// LP token symbol patterns
const LP_SYMBOL_RE = /(?:UNI-V[23]|SLP|CAKE-LP|SUSHI|crv|BPT|LP|POOL|[A-Z]+-[A-Z]+\s*LP)/i;

// Common LP token name keywords
const LP_KEYWORDS = ['uni-v', 'slp', 'cake-lp', '-lp', 'lp-', 'lpt', 'pool', 'bpt', 'crv'];

function isLpToken(transfer: AssetTransfer): boolean {
  const sym = transfer.tokenSymbol.toLowerCase();
  if (LP_KEYWORDS.some((kw) => sym.includes(kw))) return true;
  if (LP_SYMBOL_RE.test(transfer.tokenSymbol)) return true;
  return false;
}

const DEX_PROTOCOL_KEYWORDS = [
  'uniswap', 'sushiswap', 'curve', 'balancer', 'pancakeswap',
  'quickswap', 'raydium', 'orca',
];

/**
 * Detect LP add: user sends 1-2 tokens and receives LP token.
 */
export function isLpAdd(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;

  const hasLpIn = tx.assetsIn.some(isLpToken);
  const hasLpOut = tx.assetsOut.some(isLpToken);

  // Classic: send tokens, receive LP token
  if (hasLpIn && !hasLpOut) {
    const toAddr = tx.toAddress.toLowerCase();
    if (DEX_ADDRESSES.has(toAddr)) return true;
    if (
      tx.protocol &&
      DEX_PROTOCOL_KEYWORDS.some((kw) => tx.protocol!.toLowerCase().includes(kw))
    ) {
      return true;
    }
  }

  return false;
}

/**
 * Detect LP remove: user burns LP token and receives underlying tokens.
 */
export function isLpRemove(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;

  const hasLpOut = tx.assetsOut.some(isLpToken);
  const hasLpIn = tx.assetsIn.some(isLpToken);

  if (hasLpOut && !hasLpIn) {
    const toAddr = tx.toAddress.toLowerCase();
    if (DEX_ADDRESSES.has(toAddr)) return true;
    if (
      tx.protocol &&
      DEX_PROTOCOL_KEYWORDS.some((kw) => tx.protocol!.toLowerCase().includes(kw))
    ) {
      return true;
    }
  }

  return false;
}

/**
 * Classify as 'lp_add' or 'lp_remove' if applicable.
 * Returns null if rule does not apply.
 */
export function apply(tx: Transaction, _context: CategorizerContext): Transaction | null {
  const protocol = tx.protocol || resolveProtocol(tx.toAddress);

  if (isLpAdd(tx)) {
    return { ...tx, txType: 'lp_add', protocol: protocol || 'AMM' };
  }

  if (isLpRemove(tx)) {
    return { ...tx, txType: 'lp_remove', protocol: protocol || 'AMM' };
  }

  return null;
}
