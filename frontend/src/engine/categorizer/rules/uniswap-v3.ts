/**
 * Uniswap V3 concentrated liquidity position detection.
 *
 * Uni V3 positions are ERC-721 NFTs managed by the NonfungiblePositionManager.
 * Each position has a specific price range (tickLower, tickUpper).
 *
 * Lifecycle: mint -> increaseLiquidity -> decreaseLiquidity -> collect -> burn
 *
 * Tax treatment:
 * - Mint / increase: NOT taxable. Cost basis = sum of token0 + token1 at FMV.
 * - Collect fees: IS income at FMV on collection date.
 * - Decrease / burn: IS a taxable disposal. Gain/loss vs cost basis of deposited tokens.
 *
 * Key contract:
 *   NonfungiblePositionManager: 0xC36442b4a4522E871399CD717aBDD847Ab11FE88
 *
 * Ported from: src/categorizer/rules/uniswap_v3.py
 */

import type { Transaction } from '../../types';
import { resolveProtocol } from '../protocols';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

// Uniswap V3 NonfungiblePositionManager (Ethereum mainnet, same on L2s)
const UNI_V3_POSITION_MANAGER = '0xc36442b4a4522e871399cd717abdd847ab11fe88';

// Known method selectors (first 4 bytes of keccak256 of function signature)
const METHOD_SIGS: Record<string, string> = {
  '0x88316456': 'mint', // mint((address,address,uint24,int24,int24,...))
  '0x219f5d17': 'increaseLiquidity', // increaseLiquidity((uint256,uint256,...))
  '0x0c49ccbe': 'decreaseLiquidity', // decreaseLiquidity((uint256,uint128,...))
  '0xfc6f7865': 'collect', // collect((uint256,address,uint128,uint128))
  '0x42966c68': 'burn', // burn(uint256)
  '0xac9650d8': 'multicall', // multicall(bytes[])
};

// Mapping from detected method to our txType
const METHOD_TO_TYPE: Record<string, string> = {
  mint: 'uni_v3_mint',
  increaseLiquidity: 'uni_v3_increase',
  decreaseLiquidity: 'uni_v3_decrease',
  collect: 'uni_v3_collect',
  burn: 'uni_v3_burn',
};

/**
 * Extract the Uni V3 method from raw transaction input data.
 * Falls back to null if no match found.
 */
function getMethodName(tx: Transaction): string | null {
  const inputData = (tx.rawData.input as string) ?? (tx.rawData.methodId as string) ?? '';
  if (typeof inputData === 'string' && inputData.length >= 10) {
    const selector = inputData.slice(0, 10).toLowerCase();
    return METHOD_SIGS[selector] ?? null;
  }
  return null;
}

/**
 * Return true if the transaction interacts with the Uni V3 position manager.
 */
function isPositionManager(tx: Transaction): boolean {
  return tx.toAddress.toLowerCase() === UNI_V3_POSITION_MANAGER;
}

/**
 * Heuristic: classify Uni V3 action from asset flow when input data is unavailable.
 *
 * - Mint / increase: user sends 1-2 tokens, receives nothing (or NFT position)
 * - Decrease: user receives 1-2 tokens, sends nothing
 * - Collect: user receives tokens (fee collection), no send
 * - Burn: no asset flow (just destroys the NFT)
 */
function detectFromAssets(tx: Transaction): string | null {
  const hasIn = tx.assetsIn.length > 0;
  const hasOut = tx.assetsOut.length > 0;

  if (hasOut && !hasIn) {
    // Sending tokens to position manager -- mint or increase
    return 'mint';
  }
  if (hasIn && !hasOut) {
    // Receiving tokens from position manager -- could be collect or decrease
    // Without on-chain data, default to decrease (safer for tax)
    return 'decreaseLiquidity';
  }
  if (hasIn && hasOut) {
    // Both directions -- multicall combining decrease + collect
    return 'decreaseLiquidity';
  }
  if (!hasIn && !hasOut) {
    // No asset movement -- pure burn
    return 'burn';
  }
  return null;
}

/**
 * Return true if this transaction interacts with Uniswap V3 position manager.
 */
export function isUniV3(tx: Transaction): boolean {
  if (isPositionManager(tx)) return true;
  // Also check protocol name
  if (tx.protocol && tx.protocol.toLowerCase().includes('uniswap v3')) {
    if (tx.toAddress.toLowerCase() === UNI_V3_POSITION_MANAGER) {
      return true;
    }
  }
  return false;
}

/**
 * Classify Uniswap V3 position transactions.
 *
 * Returns a Transaction with txType set to one of:
 *   uni_v3_mint, uni_v3_increase, uni_v3_decrease, uni_v3_collect, uni_v3_burn
 *
 * Returns null if the rule does not apply.
 */
export function apply(tx: Transaction, _context: CategorizerContext): Transaction | null {
  if (!isPositionManager(tx)) return null;

  // Try method signature first, fall back to asset heuristic
  const method = getMethodName(tx) ?? detectFromAssets(tx);
  if (method === null) return null;

  const txType = METHOD_TO_TYPE[method] ?? 'uni_v3_mint';
  const protocol = tx.protocol || resolveProtocol(tx.toAddress) || 'Uniswap V3';

  // Extract position data from rawData if available
  const raw: Record<string, unknown> = { ...tx.rawData };
  if (!('tokenId' in raw)) {
    // Try to extract from logs
    const logs = tx.rawData.logs;
    if (Array.isArray(logs)) {
      for (const log of logs) {
        if (
          typeof log === 'object' &&
          log !== null &&
          (log as Record<string, unknown>).address &&
          ((log as Record<string, unknown>).address as string).toLowerCase() === UNI_V3_POSITION_MANAGER
        ) {
          const topics = (log as Record<string, unknown>).topics;
          if (Array.isArray(topics) && topics.length >= 2) {
            if (!('tokenId' in raw)) {
              raw.tokenId = topics[1];
            }
          }
        }
      }
    }
  }

  return {
    ...tx,
    txType,
    protocol,
    rawData: raw,
  };
}
