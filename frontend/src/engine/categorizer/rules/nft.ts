/**
 * NFT transaction detection rule.
 *
 * NFT purchases and sales ARE taxable events (capital gains/losses).
 * NFT mints: treated as acquisition at mint price.
 * NFT royalties received: ordinary income.
 *
 * Ported from: src/categorizer/rules/nft.py
 */

import type { AssetTransfer, Transaction } from '../../types';
import {
  BLUR_MARKETPLACE,
  LOOKSRARE,
  OPENSEA_SEAPORT_V1_4,
  OPENSEA_SEAPORT_V1_5,
  OPENSEA_WYVERN_V2,
  X2Y2,
  resolveProtocol,
} from '../protocols';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

const NFT_MARKETPLACE_ADDRESSES: ReadonlySet<string> = new Set([
  OPENSEA_SEAPORT_V1_5,
  OPENSEA_SEAPORT_V1_4,
  OPENSEA_WYVERN_V2,
  BLUR_MARKETPLACE,
  LOOKSRARE,
  X2Y2,
]);

/** True if any transfer looks like an ERC-721 (amount == 1 with # in symbol). */
function hasNftTransfer(transfers: AssetTransfer[]): boolean {
  return transfers.some((t) => t.tokenSymbol.includes('#'));
}

/** User buys NFT: sends ETH/token, receives NFT. */
export function isNftBuy(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;
  return hasNftTransfer(tx.assetsIn) && !hasNftTransfer(tx.assetsOut);
}

/** User sells NFT: sends NFT, receives ETH/token. */
export function isNftSell(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;
  if (hasNftTransfer(tx.assetsOut) && !hasNftTransfer(tx.assetsIn)) return true;
  // Marketplace address as tiebreaker when both sides have NFTs (rare)
  if (hasNftTransfer(tx.assetsOut) && NFT_MARKETPLACE_ADDRESSES.has(tx.toAddress.toLowerCase())) {
    return true;
  }
  return false;
}

/**
 * User mints NFT: sends ETH (to NFT contract), receives NFT.
 * Mints do not go through a marketplace.
 */
export function isNftMint(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0) return false;
  return hasNftTransfer(tx.assetsIn) && !NFT_MARKETPLACE_ADDRESSES.has(tx.toAddress.toLowerCase());
}

/**
 * Classify as 'nft_buy', 'nft_sell', or 'mint' if applicable.
 * Returns null if rule does not apply.
 */
export function apply(tx: Transaction, _context: CategorizerContext): Transaction | null {
  const protocol = tx.protocol || resolveProtocol(tx.toAddress);

  if (isNftSell(tx)) {
    return { ...tx, txType: 'nft_sell', protocol: protocol || 'NFT Marketplace' };
  }

  if (isNftBuy(tx)) {
    return { ...tx, txType: 'nft_buy', protocol: protocol || 'NFT Marketplace' };
  }

  if (isNftMint(tx)) {
    return { ...tx, txType: 'mint', protocol: protocol ?? null };
  }

  return null;
}
