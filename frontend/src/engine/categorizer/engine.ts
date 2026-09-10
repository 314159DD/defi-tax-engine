/**
 * Transaction Categorization Engine.
 *
 * Applies DeFi-specific rules in priority order to classify each transaction
 * by type and identify the correct tax treatment.
 *
 * Rule priority (highest -> lowest):
 * 1. Spam filter  -- pre-filter known spam tokens (excluded from tax)
 * 2. Self-transfer -- bridges and self-sends checked first (no tax)
 * 3. Bridge        -- cross-chain moves (no tax)
 * 4. Uni V3 LP     -- concentrated liquidity positions (mint/increase/decrease/collect/burn)
 * 5. Lending       -- Aave/Compound deposit/withdraw/liquidation
 * 6. Vault         -- Yearn/Beefy vault deposit/withdraw
 * 7. Staking       -- stake/unstake/reward (reward = income)
 * 8. LP            -- lp_add / lp_remove (lp_remove = taxable)
 * 9. NFT           -- nft_buy / nft_sell / mint
 * 10. Swap         -- DEX swap (taxable)
 * 11. Airdrop      -- receive with no send (income)
 * 12. Fallback     -- keep existing tx_type
 *
 * Ported from: src/categorizer/engine.py
 */

import type { Transaction } from '../types';
import { resolveProtocol } from './protocols';
import {
  transfer,
  bridge,
  uniswapV3,
  lending,
  vault,
  staking,
  liquidity,
  nft,
  swap,
  airdrop,
} from './rules';
import { SpamFilter } from './spam';

/** Context passed to all rules. */
export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

/**
 * Applies rule-based DeFi categorization to a list of transactions.
 */
export class CategorizerEngine {
  private readonly knownWallets: ReadonlySet<string>;
  private readonly spamFilter: SpamFilter;

  constructor(knownWallets: Set<string>, spamFilter?: SpamFilter) {
    // Normalize all wallets to lowercase
    const lower = new Set<string>(Array.from(knownWallets).map((w) => w.toLowerCase()));
    this.knownWallets = lower;
    this.spamFilter = spamFilter ?? new SpamFilter();
  }

  /**
   * Categorize a single transaction.
   * Returns a new Transaction with updated txType and protocol fields.
   */
  categorize(tx: Transaction): Transaction {
    const context: CategorizerContext = { knownWallets: this.knownWallets };
    let result: Transaction | null = null;

    // 0. Spam filter (pre-processing step)
    if (this.spamFilter.isSpam(tx)) {
      return {
        ...tx,
        txType: 'spam',
        rawData: { ...tx.rawData, spam: true },
      };
    }

    // 1. Self-transfer (no tax event)
    result = transfer.apply(tx, context);
    if (result) return result;

    // 2. Bridge (no tax event, cost basis carries over)
    result = bridge.apply(tx, context);
    if (result) return result;

    // 3. Uniswap V3 concentrated liquidity positions
    result = uniswapV3.apply(tx, context);
    if (result) return result;

    // 4. Lending rules (Aave, Compound)
    result = lending.apply(tx, context);
    if (result) return result;

    // 5. Vault rules (Yearn, Beefy, Convex)
    result = vault.apply(tx, context);
    if (result) return result;

    // 6. Staking rules (stake, unstake, reward)
    result = staking.apply(tx, context);
    if (result) return result;

    // 7. LP rules (lp_add, lp_remove)
    result = liquidity.apply(tx, context);
    if (result) return result;

    // 8. NFT rules (nft_buy, nft_sell, mint)
    result = nft.apply(tx, context);
    if (result) return result;

    // 9. Swap rules (taxable)
    result = swap.apply(tx, context);
    if (result) return result;

    // 10. Airdrop (income)
    result = airdrop.apply(tx, context);
    if (result) return result;

    // 11. Fallback: enrich protocol if possible, keep existing type
    const protocol = tx.protocol || resolveProtocol(tx.toAddress);
    if (protocol !== tx.protocol) {
      return { ...tx, protocol };
    }

    return tx;
  }

  /**
   * Categorize a list of transactions.
   * Logs a summary of type counts when done.
   */
  categorizeAll(transactions: Transaction[]): Transaction[] {
    const results: Transaction[] = [];
    for (const tx of transactions) {
      try {
        const categorized = this.categorize(tx);
        results.push(categorized);
      } catch (exc) {
        console.warn(`Failed to categorize tx ${tx.txHash}:`, exc);
        results.push(tx); // keep original on error
      }
    }
    this.logSummary(results);
    return results;
  }

  private logSummary(transactions: Transaction[]): void {
    const counts: Record<string, number> = {};
    for (const tx of transactions) {
      counts[tx.txType] = (counts[tx.txType] ?? 0) + 1;
    }
    const total = transactions.length;
    const categorized = total - (counts.unknown ?? 0);
    const pct = total > 0 ? ((categorized / total) * 100).toFixed(1) : '0.0';
    const breakdown = Object.entries(counts)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join(', ');
    console.info(
      `Categorized ${categorized}/${total} transactions (${pct}%). Breakdown: ${breakdown}`,
    );
  }
}

// -- Convenience functions --

/**
 * Categorize a list of transactions with the given wallet set.
 */
export function categorizeTransactions(
  transactions: Transaction[],
  knownWallets: Set<string>,
): Transaction[] {
  const engine = new CategorizerEngine(knownWallets);
  return engine.categorizeAll(transactions);
}

// -- Tax event helpers --

export const TAXABLE_TYPES: ReadonlySet<string> = new Set([
  'swap',
  'lp_remove',
  'nft_sell',
  'uni_v3_decrease',
  'vault_withdraw',
  'lending_withdraw',
  'lending_liquidation',
]);

export const INCOME_TYPES: ReadonlySet<string> = new Set([
  'reward',
  'airdrop',
  'uni_v3_collect',
]);

export const NON_TAXABLE_TYPES: ReadonlySet<string> = new Set([
  'transfer',
  'bridge',
  'stake',
  'unstake',
  'lp_add',
  'nft_buy',
  'mint',
  'approve',
  'unknown',
  'spam',
  'uni_v3_mint',
  'uni_v3_increase',
  'uni_v3_burn',
  'vault_deposit',
  'lending_deposit',
]);

/** Return true if this transaction triggers a capital gain/loss calculation. */
export function isTaxableDisposal(tx: Transaction): boolean {
  return TAXABLE_TYPES.has(tx.txType);
}

/** Return true if this transaction is ordinary income (staking reward, airdrop). */
export function isIncomeEvent(tx: Transaction): boolean {
  return INCOME_TYPES.has(tx.txType);
}
