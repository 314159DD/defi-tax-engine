/**
 * Staking transaction detection rules.
 *
 * Stake:   user sends tokens to staking contract. NOT immediately taxable.
 * Unstake: user receives tokens back from staking. NOT taxable if same token.
 * Reward:  user receives staking reward tokens. IS income (ordinary).
 *
 * Ported from: src/categorizer/rules/staking.py
 */

import type { Transaction } from '../../types';
import { STAKING_ADDRESSES, resolveProtocol } from '../protocols';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

// Known staking reward token symbols
const REWARD_SYMBOLS: ReadonlySet<string> = new Set([
  'LDO', 'RPL', 'CVX', 'CRV', 'AAVE', 'COMP', 'MKR',
  'SNX', 'FXS', 'ANKR', 'RETH', 'STETH', 'WSTETH',
  'CBETH', 'FRXETH', 'SFRXETH',
]);

// Known liquid staking deposit symbols (stake ETH -> get stToken)
const LIQUID_STAKE_IN_SYMBOLS: ReadonlySet<string> = new Set([
  'ETH', 'WETH', 'MATIC', 'BNB', 'SOL',
]);

const LIQUID_STAKE_OUT_SYMBOLS: ReadonlySet<string> = new Set([
  'STETH', 'WSTETH', 'RETH', 'CBETH', 'FRXETH', 'SFRXETH',
  'STMATIC', 'BMATIC', 'MSOL', 'STSOL', 'JITOSOL',
]);

function toStakingContract(tx: Transaction): boolean {
  return STAKING_ADDRESSES.has(tx.toAddress.toLowerCase());
}

function protocolIsStaking(tx: Transaction): boolean {
  if (!tx.protocol) return false;
  const lower = tx.protocol.toLowerCase();
  return ['lido', 'rocket', 'rocketpool', 'frax', 'convex',
          'yearn', 'beefy', 'stake', 'staking'].some((kw) => lower.includes(kw));
}

function setsIntersect(a: ReadonlySet<string>, b: ReadonlySet<string>): boolean {
  let found = false;
  a.forEach((item) => {
    if (b.has(item)) found = true;
  });
  return found;
}

/**
 * User deposits tokens into staking contract (no reward yet).
 */
export function isStake(tx: Transaction): boolean {
  if (tx.assetsOut.length === 0) return false;
  if (!toStakingContract(tx) && !protocolIsStaking(tx)) return false;

  const outSymbols = new Set(tx.assetsOut.map((t) => t.tokenSymbol.toUpperCase()));
  const inSymbols = new Set(tx.assetsIn.map((t) => t.tokenSymbol.toUpperCase()));

  // Liquid staking: send ETH, get stETH/rETH etc.
  if (setsIntersect(outSymbols, LIQUID_STAKE_IN_SYMBOLS) && setsIntersect(inSymbols, LIQUID_STAKE_OUT_SYMBOLS)) {
    return true;
  }

  // Plain stake: send tokens, receive nothing (or a position token)
  if (tx.assetsOut.length > 0 && tx.assetsIn.length === 0) {
    return true;
  }

  return false;
}

/**
 * User withdraws staked tokens (not reward collection).
 */
export function isUnstake(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0) return false;
  if (!toStakingContract(tx) && !protocolIsStaking(tx)) return false;

  const outSymbols = new Set(tx.assetsOut.map((t) => t.tokenSymbol.toUpperCase()));
  const inSymbols = new Set(tx.assetsIn.map((t) => t.tokenSymbol.toUpperCase()));

  // Liquid unstake: send stETH/rETH, get ETH back
  if (setsIntersect(outSymbols, LIQUID_STAKE_OUT_SYMBOLS) && setsIntersect(inSymbols, LIQUID_STAKE_IN_SYMBOLS)) {
    return true;
  }

  // Plain unstake: receive tokens, send nothing
  if (tx.assetsIn.length > 0 && tx.assetsOut.length === 0) {
    return true;
  }

  return false;
}

/**
 * User claims staking rewards.
 *
 * Indicators:
 * 1. Receives tokens from a staking contract with no corresponding send
 * 2. Token symbol is a known reward token
 * 3. No assetsOut (pure claim)
 */
export function isStakingReward(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length > 0) return false;

  if (toStakingContract(tx) || protocolIsStaking(tx)) return true;

  // Fallback: any incoming transfer of known reward tokens with no outgoing
  const inSymbols = new Set(tx.assetsIn.map((t) => t.tokenSymbol.toUpperCase()));
  if (setsIntersect(inSymbols, REWARD_SYMBOLS)) return true;

  return false;
}

/**
 * Classify as 'stake', 'unstake', or 'reward' if applicable.
 * Returns null if rule does not apply.
 */
export function apply(tx: Transaction, _context: CategorizerContext): Transaction | null {
  const protocol = tx.protocol || resolveProtocol(tx.toAddress);

  if (isStakingReward(tx)) {
    return { ...tx, txType: 'reward', protocol: protocol || 'Staking' };
  }

  if (isStake(tx)) {
    return { ...tx, txType: 'stake', protocol: protocol || 'Staking' };
  }

  if (isUnstake(tx)) {
    return { ...tx, txType: 'unstake', protocol: protocol || 'Staking' };
  }

  return null;
}
