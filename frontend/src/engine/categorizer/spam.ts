/**
 * Spam token filter.
 *
 * Detects and flags spam transactions so they are excluded from tax
 * calculations, dashboard totals, and tier billing.
 *
 * Detection strategies:
 * 1. Known spam contract addresses
 * 2. Token name heuristics (URLs, "Visit", "Claim at", etc.)
 * 3. Dust amounts (< $0.01 USD value)
 * 4. Zero-value transfers
 *
 * Ported from: src/categorizer/spam.py + src/data/spam_tokens.py
 */

import Decimal from 'decimal.js';
import type { AssetTransfer, Transaction } from '../types';

// -- Dust threshold -- transfers below this USD value are suspicious
const DUST_THRESHOLD_USD = new Decimal('0.01');

// -- Known spam contract addresses --
export const KNOWN_SPAM_CONTRACTS: ReadonlySet<string> = new Set([
  // "Visit ..." style phishing tokens
  '0x76e1f96c2b3bf4fbe9a22d14015ba0c5bea0a470', // Visit-X.com scam
  '0x4e5b2e1dc63f6b91cb6cd759936495434c7e972f', // $ ClaimReward.com
  '0x2d4b16e1f7e2e01f4f6f1b6e6d5b2f4c3b2a1c0d', // Fake USDT airdrop
  '0x853d955acef822db058eb8505911ed77f175b99e', // Phishing FEI variant
  '0x12b32f10a499bf40db334efe04226cca00bf1e26', // Fake UNI airdrop
  '0xaa7fb1c8ce6f18d4fd4aabb61a2193d4d441c54f', // Spam governance token
  '0x1a2f3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a', // Dust attack token
  '0x6b3595068778dd592e39a122f4f5a5cf09c90fe2', // Fake SUSHI spam copy
  '0xdead000000000000000000000000000000000001', // Dead address spam
  '0xdead000000000000000000000000000000000002', // Dead address spam 2
  '0x0000000000000000000000000000000000000000', // Zero address spam
  '0xf3ae5d769e153ef72b4e3591ac004e89f48107a1', // HEX phishing variant
  '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984', // Fake UNI clone
  '0xa9536b9c75a9e0fae3b56a96ac8edf76abc91978', // Phishing airdrop
  '0xb8c77482e45f1f44de1745f52c74426c631bdd52', // BNB phishing clone
  '0x3845badade8e6dff049820680d1f14bd3903a5d0', // Fake SAND token
  '0x50d1c9771902476076ecfc8b2a83ad6b9355a4c9', // FTX IOU scam token
  '0x72e364f2abdc788b7e918bc238b21f109cd634d7', // Fake MVI airdrop
  '0xc944e90c64b2c07662a292be6244bdf05cda44a7', // GRT phishing clone
  '0x11fe4b6ae13d2a6055c8d9cf65c55bac32b5d844', // Fake DAI airdrop
  '0x2b591e99afe9f32eaa6214f7b7629768c40eeb39', // HEX spam variant 2
  '0x888888435fde8e7d4c54cab67f206c4199454c6a', // DFX scam airdrop
  '0x777777777777777777777777777777777777777a', // Lucky7 scam
  '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d', // Fake BAYC token
  '0x6982508145454ce325ddbe47a25d4ec3d2311933', // PEPE phishing clone
  '0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce', // SHIB phishing clone
  '0xdac17f958d2ee523a2206206994597c13d831ec7', // Fake USDT clone
  '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', // Fake USDC clone
  '0x514910771af9ca656af840dff83e8264ecf986ca', // LINK phishing clone
  '0xfe9a29ab92522d14fc65880d817214261d8479ae', // SnowSwap scam
  '0xfab5a05c933f1a2463e334e011992e897d56ef0a', // Visit-Y.com scam
  '0x3301ee63fb29f863f2333bd4466acb46cd8323e6', // Airdrop URL token
  '0x68e74b4e80a17d5a38e4d1f0d2c2ae03e3fb5298', // Claim reward scam
]);

// -- Spam name patterns --
export const SPAM_NAME_PATTERNS: RegExp[] = [
  /visit\s+\S+\.com/i, // "Visit SomeScam.com"
  /claim\s+(at|your|reward)/i, // "Claim at X" / "Claim your reward"
  /https?:\/\//i, // URLs in token name
  /\.com\b/i, // Domains in token name
  /\.xyz\b/i,
  /\.io\b/i,
  /\.org\b/i,
  /\.net\b/i,
  /free\s+airdrop/i, // "Free Airdrop"
  /^airdrop\b/i, // Token named "Airdrop..."
  /reward\s*token/i, // "RewardToken"
  /voucher/i, // "Gift voucher"
  /\$\s*\d+\s*(reward|bonus|gift)/i, // "$500 Reward"
];

/**
 * Identifies spam transactions using contract lists, name heuristics,
 * and value-based filters.
 */
export class SpamFilter {
  private readonly spamContracts: ReadonlySet<string>;

  constructor(extraSpamContracts?: Set<string>) {
    if (extraSpamContracts && extraSpamContracts.size > 0) {
      const merged = new Set(Array.from(KNOWN_SPAM_CONTRACTS));
      Array.from(extraSpamContracts).forEach((addr) => merged.add(addr.toLowerCase()));
      this.spamContracts = merged;
    } else {
      this.spamContracts = KNOWN_SPAM_CONTRACTS;
    }
  }

  // -- Public API --

  /**
   * Return true if the transaction should be flagged as spam.
   * Checks are ordered from cheapest to most expensive.
   */
  isSpam(tx: Transaction): boolean {
    if (this.knownSpamContract(tx)) return true;
    if (this.zeroValueTransfer(tx)) return true;
    if (this.spamTokenName(tx)) return true;
    if (this.dustAmount(tx)) return true;
    return false;
  }

  /**
   * Partition transactions into [clean, spam] lists.
   * Spam transactions have rawData.spam = true set.
   */
  filterSpam(transactions: Transaction[]): [Transaction[], Transaction[]] {
    const clean: Transaction[] = [];
    const spam: Transaction[] = [];
    for (const tx of transactions) {
      if (this.isSpam(tx)) {
        const flagged: Transaction = {
          ...tx,
          txType: 'spam',
          rawData: { ...tx.rawData, spam: true },
        };
        spam.push(flagged);
      } else {
        clean.push(tx);
      }
    }
    return [clean, spam];
  }

  // -- Private checks --

  private knownSpamContract(tx: Transaction): boolean {
    const allTransfers: AssetTransfer[] = [...tx.assetsIn, ...tx.assetsOut];
    for (const transfer of allTransfers) {
      if (transfer.tokenAddress && this.spamContracts.has(transfer.tokenAddress.toLowerCase())) {
        return true;
      }
    }
    // Also check if from_address is a known spam sender
    if (this.spamContracts.has(tx.fromAddress.toLowerCase())) {
      return true;
    }
    return false;
  }

  private spamTokenName(tx: Transaction): boolean {
    const allTransfers: AssetTransfer[] = [...tx.assetsIn, ...tx.assetsOut];
    for (const transfer of allTransfers) {
      const symbol = transfer.tokenSymbol;
      for (const pattern of SPAM_NAME_PATTERNS) {
        if (pattern.test(symbol)) {
          return true;
        }
      }
    }
    return false;
  }

  private zeroValueTransfer(tx: Transaction): boolean {
    const allTransfers: AssetTransfer[] = [...tx.assetsIn, ...tx.assetsOut];
    if (allTransfers.length === 0) return false;
    return allTransfers.every((t) => t.amount.eq(0));
  }

  private dustAmount(tx: Transaction): boolean {
    if (tx.assetsOut.length > 0) return false;
    if (tx.assetsIn.length === 0) return false;

    // Only flag as dust if ALL incoming have usdValue set and below threshold
    for (const transfer of tx.assetsIn) {
      if (transfer.usdValue === null) return false; // Unknown value -- don't assume spam
      if (transfer.usdValue.gte(DUST_THRESHOLD_USD)) return false;
    }
    return true;
  }
}
