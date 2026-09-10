/**
 * Cost Basis Calculation Engine.
 *
 * Walks transactions in chronological order, builds a TaxLot book,
 * and produces Disposals for every taxable event.
 *
 * DeFi-specific rules implemented here:
 *   - swap          -> disposal of token_out, acquisition of token_in
 *   - lp_add        -> disposal of deposited tokens (at cost basis), acquisition of LP token
 *   - lp_remove     -> disposal of LP token, acquisition of underlying tokens
 *   - reward/airdrop-> acquisition at FMV (income event, cost basis = FMV)
 *   - bridge        -> NO disposal; cost basis carries over
 *   - transfer      -> NO disposal (self-transfer between own wallets)
 *   - stake/unstake -> NO disposal; cost basis carries over
 *   - Gas fees      -> added to cost basis of acquisition; deducted from proceeds on disposal
 *
 * Ported from: src/calculator/engine.py
 *
 * CRITICAL: All arithmetic uses decimal.js Decimal methods - NEVER native JS operators on money.
 */

import Decimal from 'decimal.js';
import type {
  Transaction,
  AssetTransfer,
  TaxLot,
  Disposal,
  LotConsumption,
  TaxSummary,
} from '../types';
import { LotManager, blendedHoldingPeriod, type CostBasisMethod } from './lots';

const ZERO = new Decimal('0');

/** Generate a UUID without requiring the `uuid` package. */
function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback for older environments
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function transferUsd(fee: AssetTransfer | null): Decimal {
  if (fee === null || fee.usdValue === null) return ZERO;
  return fee.usdValue;
}

function isGasTokenForFee(
  asset: AssetTransfer,
  fee: AssetTransfer | null,
): boolean {
  if (fee === null) return false;
  return asset.tokenSymbol === fee.tokenSymbol;
}

// ---------------------------------------------------------------------------
// CalculatorEngine
// ---------------------------------------------------------------------------

export interface CalculateResult {
  disposals: Disposal[];
  lots: TaxLot[];
  summary: TaxSummary;
}

export class CalculatorEngine {
  private readonly method: CostBasisMethod;
  private readonly knownWallets: Set<string>;

  /**
   * @param transactions  Not stored - passed to calculate().
   * @param method        'FIFO', 'LIFO', or 'HIFO'.
   * @param knownWallets  Wallet addresses owned by the user (for self-transfer detection).
   */
  constructor(
    private readonly transactions: Transaction[],
    method: CostBasisMethod,
    knownWallets: string[],
  ) {
    const upper = method.toUpperCase() as CostBasisMethod;
    if (!['FIFO', 'LIFO', 'HIFO'].includes(upper)) {
      throw new Error(`Unknown method: '${method}'. Choose FIFO, LIFO, or HIFO.`);
    }
    this.method = upper;
    this.knownWallets = new Set(knownWallets.map((w) => w.toLowerCase()));
  }

  /**
   * Process all transactions and return disposals, lots, and a tax summary.
   *
   * @param year  If set, return only disposals from this calendar year.
   *              Lots from prior years are still built up correctly.
   */
  calculate(year?: number): CalculateResult {
    // Sort chronologically - critical for correct lot ordering
    const sortedTxs = [...this.transactions].sort((a, b) => {
      if (a.timestamp < b.timestamp) return -1;
      if (a.timestamp > b.timestamp) return 1;
      return 0;
    });

    const lotManager = new LotManager();
    const disposals: Disposal[] = [];

    for (let i = 0; i < sortedTxs.length; i++) {
      const tx = sortedTxs[i];

      // Progress reporting: post message every 1000 transactions (for Web Worker)
      if (i > 0 && i % 1000 === 0) {
        try {
          if (typeof self !== 'undefined' && typeof self.postMessage === 'function') {
            self.postMessage({
              type: 'progress',
              processed: i,
              total: sortedTxs.length,
            });
          }
        } catch {
          // Not in a worker context - ignore
        }
      }

      try {
        const newDisposals = this._processTransaction(tx, lotManager);
        disposals.push(...newDisposals);
      } catch (err) {
        console.warn(
          `Error processing tx ${tx.txHash} (${tx.txType}): ${err instanceof Error ? err.message : err} -- skipping`,
        );
      }
    }

    // Filter by year if specified
    let filtered = disposals;
    if (year !== undefined) {
      filtered = disposals.filter((d) => {
        const dYear = new Date(d.date).getFullYear();
        return dYear === year;
      });
    }

    // Build summary
    const summary = this._buildSummary(filtered);

    return {
      disposals: filtered,
      lots: lotManager.getAllLots(),
      summary,
    };
  }

  // ── Transaction dispatch ──────────────────────────────────────────

  private _processTransaction(
    tx: Transaction,
    lm: LotManager,
  ): Disposal[] {
    const t = tx.txType;

    if (['transfer', 'bridge', 'approve', 'unknown'].includes(t)) {
      // Non-taxable: transfer cost basis as-is
      return [];
    }

    if (['stake', 'unstake'].includes(t)) {
      // Staking itself is not a disposal
      return [];
    }

    if (t === 'swap') {
      return this._handleSwap(tx, lm);
    }

    if (t === 'lp_add') {
      this._handleLpAdd(tx, lm);
      return [];
    }

    if (t === 'lp_remove') {
      return this._handleLpRemove(tx, lm);
    }

    if (['reward', 'airdrop'].includes(t)) {
      this._handleIncome(tx, lm);
      return [];
    }

    if (['nft_buy', 'mint'].includes(t)) {
      this._handleNftBuy(tx, lm);
      return [];
    }

    if (t === 'nft_sell') {
      return this._handleNftSell(tx, lm);
    }

    // Fallback: if there are assetsIn, treat as acquisition
    if (tx.assetsIn.length > 0) {
      this._handleGenericAcquisition(tx, lm);
    }
    return [];
  }

  // ── Swap ──────────────────────────────────────────────────────────

  private _handleSwap(tx: Transaction, lm: LotManager): Disposal[] {
    const disposals: Disposal[] = [];
    const gasUsd = transferUsd(tx.fee);

    // Dispose of each token sent out
    for (const assetOut of tx.assetsOut) {
      if (isGasTokenForFee(assetOut, tx.fee)) continue;
      if (assetOut.usdValue === null) {
        console.warn(
          `Swap ${tx.txHash}: missing USD value for ${assetOut.tokenSymbol} out -- skipping disposal`,
        );
        continue;
      }

      let proceeds = assetOut.usdValue;
      // If this is the only asset_out and gas is known, gas reduces proceeds
      if (tx.assetsOut.length === 1) {
        proceeds = proceeds.minus(gasUsd);
      }

      try {
        const disposal = this._consume(
          lm,
          assetOut.tokenSymbol,
          assetOut.amount,
          Decimal.max(proceeds, ZERO),
          tx.timestamp,
          tx.txHash,
        );
        disposals.push(disposal);
      } catch (err) {
        console.warn(`Swap ${tx.txHash}: ${err instanceof Error ? err.message : err}`);
      }
    }

    // Acquire each token received
    const gasPerToken = tx.assetsIn.length > 0
      ? gasUsd.dividedBy(tx.assetsIn.length)
      : ZERO;

    for (const assetIn of tx.assetsIn) {
      const fmv = assetIn.usdValue ?? ZERO;
      const costBasis = fmv.plus(gasPerToken);

      lm.addLot({
        id: newId(),
        token: assetIn.tokenSymbol,
        amount: assetIn.amount,
        costBasisUsd: costBasis,
        acquisitionDate: tx.timestamp,
        remaining: assetIn.amount,
        source: 'swap',
        txHash: tx.txHash,
        spekulationsfristEnd: null,
      });
    }

    return disposals;
  }

  // ── LP add ────────────────────────────────────────────────────────

  private _handleLpAdd(tx: Transaction, lm: LotManager): void {
    let totalDepositBasis = ZERO;

    for (const assetOut of tx.assetsOut) {
      if (assetOut.usdValue !== null) {
        totalDepositBasis = totalDepositBasis.plus(assetOut.usdValue);
      } else {
        // Try to consume from existing lots to derive cost basis
        try {
          const consumptions = lm.consumeLots(
            assetOut.tokenSymbol,
            assetOut.amount,
            'FIFO',
          );
          const cost = consumptions.reduce(
            (sum, c) => sum.plus(c.costBasisConsumed),
            ZERO,
          );
          totalDepositBasis = totalDepositBasis.plus(cost);
        } catch {
          console.warn(
            `LP add ${tx.txHash}: no lots or USD value for ${assetOut.tokenSymbol} -- using 0 for that leg`,
          );
        }
      }
    }

    // Record LP token acquisition
    for (const assetIn of tx.assetsIn) {
      if (assetIn.amount.isZero()) continue;
      lm.addLot({
        id: newId(),
        token: assetIn.tokenSymbol,
        amount: assetIn.amount,
        costBasisUsd: totalDepositBasis,
        acquisitionDate: tx.timestamp,
        remaining: assetIn.amount,
        source: 'lp_add',
        txHash: tx.txHash,
        spekulationsfristEnd: null,
      });
    }
  }

  // ── LP remove ─────────────────────────────────────────────────────

  private _handleLpRemove(tx: Transaction, lm: LotManager): Disposal[] {
    const disposals: Disposal[] = [];

    // Total FMV of tokens received = proceeds of LP disposal
    let totalProceeds = ZERO;
    for (const assetIn of tx.assetsIn) {
      if (assetIn.usdValue !== null) {
        totalProceeds = totalProceeds.plus(assetIn.usdValue);
      }
    }

    // Dispose LP tokens
    for (const assetOut of tx.assetsOut) {
      if (assetOut.usdValue === null && totalProceeds.isZero()) {
        console.warn(`LP remove ${tx.txHash}: no USD value for proceeds -- skipping`);
        continue;
      }

      const proceeds = assetOut.usdValue === null ? totalProceeds : assetOut.usdValue;

      try {
        const disposal = this._consume(
          lm,
          assetOut.tokenSymbol,
          assetOut.amount,
          proceeds,
          tx.timestamp,
          tx.txHash,
        );
        disposals.push(disposal);
      } catch (err) {
        console.warn(`LP remove ${tx.txHash}: ${err instanceof Error ? err.message : err}`);
      }
    }

    // Acquire underlying tokens at their FMV
    for (const assetIn of tx.assetsIn) {
      const fmv = assetIn.usdValue ?? ZERO;
      lm.addLot({
        id: newId(),
        token: assetIn.tokenSymbol,
        amount: assetIn.amount,
        costBasisUsd: fmv,
        acquisitionDate: tx.timestamp,
        remaining: assetIn.amount,
        source: 'lp_remove',
        txHash: tx.txHash,
        spekulationsfristEnd: null,
      });
    }

    return disposals;
  }

  // ── Income events (reward, airdrop) ───────────────────────────────

  private _handleIncome(tx: Transaction, lm: LotManager): void {
    for (const assetIn of tx.assetsIn) {
      const fmv = assetIn.usdValue ?? ZERO;
      lm.addLot({
        id: newId(),
        token: assetIn.tokenSymbol,
        amount: assetIn.amount,
        costBasisUsd: fmv,
        acquisitionDate: tx.timestamp,
        remaining: assetIn.amount,
        source: tx.txType, // "reward" or "airdrop"
        txHash: tx.txHash,
        spekulationsfristEnd: null,
      });
    }
  }

  // ── NFT buy / sell ────────────────────────────────────────────────

  private _handleNftBuy(tx: Transaction, lm: LotManager): void {
    const gasUsd = transferUsd(tx.fee);

    for (const assetIn of tx.assetsIn) {
      const fmv = assetIn.usdValue ?? ZERO;
      lm.addLot({
        id: newId(),
        token: assetIn.tokenSymbol,
        amount: assetIn.amount,
        costBasisUsd: fmv.plus(gasUsd),
        acquisitionDate: tx.timestamp,
        remaining: assetIn.amount,
        source: 'nft_buy',
        txHash: tx.txHash,
        spekulationsfristEnd: null,
      });
    }

    // ETH/SOL paid out is consumed from existing lots
    for (const assetOut of tx.assetsOut) {
      if (assetOut.usdValue === null) continue;
      try {
        this._consume(
          lm,
          assetOut.tokenSymbol,
          assetOut.amount,
          assetOut.usdValue,
          tx.timestamp,
          tx.txHash,
        );
      } catch (err) {
        console.warn(`NFT buy ${tx.txHash}: ${err instanceof Error ? err.message : err}`);
      }
    }
  }

  private _handleNftSell(tx: Transaction, lm: LotManager): Disposal[] {
    const disposals: Disposal[] = [];
    const gasUsd = transferUsd(tx.fee);

    for (const assetOut of tx.assetsOut) {
      if (assetOut.usdValue === null) continue;
      const proceeds = assetOut.usdValue.minus(gasUsd);
      try {
        const disposal = this._consume(
          lm,
          assetOut.tokenSymbol,
          assetOut.amount,
          Decimal.max(proceeds, ZERO),
          tx.timestamp,
          tx.txHash,
        );
        disposals.push(disposal);
      } catch (err) {
        console.warn(`NFT sell ${tx.txHash}: ${err instanceof Error ? err.message : err}`);
      }
    }
    return disposals;
  }

  // ── Generic acquisition fallback ──────────────────────────────────

  private _handleGenericAcquisition(tx: Transaction, lm: LotManager): void {
    for (const assetIn of tx.assetsIn) {
      const fmv = assetIn.usdValue ?? ZERO;
      lm.addLot({
        id: newId(),
        token: assetIn.tokenSymbol,
        amount: assetIn.amount,
        costBasisUsd: fmv,
        acquisitionDate: tx.timestamp,
        remaining: assetIn.amount,
        source: tx.txType,
        txHash: tx.txHash,
        spekulationsfristEnd: null,
      });
    }
  }

  // ── Internal consume dispatcher ───────────────────────────────────

  private _consume(
    lm: LotManager,
    token: string,
    amount: Decimal,
    proceedsUsd: Decimal,
    disposalDate: string,
    txHash: string,
  ): Disposal {
    const consumptions = lm.consumeLots(token, amount, this.method);

    const totalCost = consumptions.reduce(
      (sum, c) => sum.plus(c.costBasisConsumed),
      ZERO,
    );

    const gainLoss = proceedsUsd.minus(totalCost);
    const hp = blendedHoldingPeriod(consumptions, disposalDate, amount);

    return {
      id: newId(),
      date: disposalDate,
      token,
      amount,
      proceedsUsd,
      costBasisUsd: totalCost,
      gainLossUsd: gainLoss,
      holdingPeriod: hp,
      method: this.method,
      lotsConsumed: consumptions,
      txHash,
      exemption: null,
      holdingPeriodEnum: null,
      citationCode: null,
      citationText: null,
      citationSource: null,
      isGrayArea: false,
    };
  }

  // ── Summary builder ───────────────────────────────────────────────

  private _buildSummary(disposals: Disposal[]): TaxSummary {
    let totalGains = ZERO;
    let totalLosses = ZERO;
    let shortTermGains = ZERO;
    let longTermGains = ZERO;
    let exemptGains = ZERO;

    for (const d of disposals) {
      if (d.gainLossUsd.greaterThan(ZERO)) {
        totalGains = totalGains.plus(d.gainLossUsd);
      } else {
        totalLosses = totalLosses.plus(d.gainLossUsd);
      }

      if (d.holdingPeriod === 'short-term') {
        shortTermGains = shortTermGains.plus(d.gainLossUsd);
      } else if (d.holdingPeriod === 'long-term') {
        longTermGains = longTermGains.plus(d.gainLossUsd);
      } else if (d.holdingPeriod === 'exempt') {
        exemptGains = exemptGains.plus(d.gainLossUsd);
      }
    }

    const net = totalGains.plus(totalLosses);

    return {
      totalGains,
      totalLosses,
      net,
      shortTermGains,
      longTermGains,
      exemptGains,
      taxLiability: ZERO, // computed by tax module, not the engine
      exemptions: [],
      incomeTotal: ZERO, // income events are tracked separately
    };
  }
}
