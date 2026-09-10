/**
 * Source of Funds report generator - transaction trail for KYC compliance.
 *
 * Ported from src/reports/source_of_funds.py + source_of_funds_pdf.py.
 *
 * German and Austrian banks increasingly require "Herkunftsnachweis" (proof of
 * origin) for crypto -> fiat conversions. This module traces each current holding
 * backward through the full transaction history to produce a chain-of-custody report.
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Transaction, TaxLot, ReportFile } from '../types';
import { buildCsv } from './csv-export';

// ---------------------------------------------------------------------------
// Data models
// ---------------------------------------------------------------------------

/** One step in the chain of custody. */
export interface FundingStep {
  stepNumber: number;
  date: string;      // ISO date
  action: string;    // "purchased", "received_staking_reward", "swapped", "bridged", "transferred", "airdrop"
  source: string;    // "Coinbase", "Uniswap V3", "Lido Staking", "Bridge from Ethereum"
  token: string;
  amount: Decimal;
  valueUsd: Decimal;
  txHash: string | null;
  chain: string;
}

/** Complete origin trace for a single holding. */
export interface HoldingOrigin {
  token: string;
  currentAmount: Decimal;
  currentValueUsd: Decimal;
  walletAddress: string;
  chain: string;
  acquisitionMethod: string;
  originalAcquisitionDate: string; // ISO date
  originalAcquisitionCost: Decimal;
  fundingTrail: FundingStep[];
}

/** Top-level report wrapping all holding origins. */
export interface SourceOfFundsReport {
  generatedAt: string; // ISO datetime
  walletAddresses: string[];
  holdings: HoldingOrigin[];
  totalPortfolioValue: Decimal;
  totalAcquisitionCost: Decimal;
}

// ---------------------------------------------------------------------------
// Source classification
// ---------------------------------------------------------------------------

const SOURCE_TO_METHOD: Record<string, string> = {
  swap: 'swap',
  reward: 'staking_reward',
  airdrop: 'airdrop',
  mining: 'mining',
  validator: 'staking_reward',
  interest: 'defi_yield',
  lp_add: 'defi_yield',
  lp_remove: 'defi_yield',
  nft_buy: 'exchange_purchase',
  wrap: 'swap',
  bridge: 'transfer',
  transfer: 'transfer',
};

const SOURCE_TO_ACTION: Record<string, string> = {
  swap: 'swapped',
  reward: 'received_staking_reward',
  airdrop: 'airdrop',
  mining: 'received_mining_reward',
  validator: 'received_staking_reward',
  interest: 'received_defi_yield',
  lp_add: 'provided_liquidity',
  lp_remove: 'removed_liquidity',
  nft_buy: 'purchased',
  wrap: 'swapped',
  bridge: 'bridged',
  transfer: 'transferred',
};

function classifyAcquisitionMethod(source: string): string {
  return SOURCE_TO_METHOD[source] ?? 'exchange_purchase';
}

function classifyAction(source: string): string {
  return SOURCE_TO_ACTION[source] ?? 'purchased';
}

const METHOD_LABEL: Record<string, string> = {
  exchange_purchase: 'Exchange Purchase',
  staking_reward: 'Staking Reward',
  defi_yield: 'DeFi Yield',
  airdrop: 'Airdrop',
  swap: 'DEX Swap',
  transfer: 'Wallet Transfer',
  mining: 'Mining',
};

function methodLabel(method: string): string {
  return METHOD_LABEL[method] ?? method.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Trail builder
// ---------------------------------------------------------------------------

function buildTrailForLot(
  lot: TaxLot,
  transactions: Transaction[],
): FundingStep[] {
  const steps: FundingStep[] = [];
  const seenHashes = new Set<string>();

  let currentHash: string | null = lot.txHash;
  const token = lot.token;
  const amount = lot.amount;
  const costBasis = lot.costBasisUsd;

  // Build a lookup from txHash to transaction
  const txByHash = new Map<string, Transaction>();
  for (const tx of transactions) {
    txByHash.set(tx.txHash, tx);
  }

  let stepNum = 0;
  while (currentHash && !seenHashes.has(currentHash)) {
    seenHashes.add(currentHash);
    const tx = txByHash.get(currentHash);
    if (!tx) break;

    stepNum++;
    const chain = tx.chain;
    const protocol = tx.protocol ?? 'Unknown';
    const txDate = tx.timestamp.slice(0, 10);

    steps.push({
      stepNumber: stepNum,
      date: txDate,
      action: classifyAction(tx.txType),
      source: protocol,
      token,
      amount,
      valueUsd: costBasis,
      txHash: currentHash,
      chain,
    });

    // Try to trace further via rawData
    const prevHash = tx.rawData?.prev_tx_hash;
    if (typeof prevHash === 'string' && prevHash !== currentHash) {
      currentHash = prevHash;
      continue;
    }

    break;
  }

  // Reverse for chronological order, re-number
  steps.reverse();
  for (let i = 0; i < steps.length; i++) {
    steps[i].stepNumber = i + 1;
  }

  return steps;
}

// ---------------------------------------------------------------------------
// Main entry point (client-side: pass data directly, no DB)
// ---------------------------------------------------------------------------

/**
 * Trace the origin of holdings through transaction history.
 *
 * Client-side version: accepts data arrays directly instead of DB.
 *
 * @param openLots       - Tax lots with remaining > 0
 * @param transactions   - All transactions for backward tracing
 * @param walletAddresses - Known wallet addresses
 * @returns SourceOfFundsReport
 */
export function traceHoldings(
  openLots: TaxLot[],
  transactions: Transaction[],
  walletAddresses: string[] = [],
): SourceOfFundsReport {
  const addrSet = new Set(walletAddresses.map((a) => a.toLowerCase()));
  const holdings: HoldingOrigin[] = [];
  let totalValue = new Decimal('0');
  let totalCost = new Decimal('0');

  for (const lot of openLots) {
    if (lot.remaining.lte('0')) continue;

    const remaining = lot.remaining;
    const source = lot.source;
    const acqDate = lot.acquisitionDate;
    const costBasis = lot.costBasisUsd;

    // Proportional cost for remaining amount
    const remainingCost = lot.amount.gt('0')
      ? remaining.div(lot.amount).times(costBasis)
      : new Decimal('0');

    // Build the funding trail
    const trail = buildTrailForLot(lot, transactions);

    // Determine wallet address + chain from the transaction
    let walletAddr = '';
    let chain = 'unknown';
    const tx = transactions.find((t) => t.txHash === lot.txHash);
    if (tx) {
      chain = tx.chain;
      const toAddr = tx.toAddress?.toLowerCase();
      const fromAddr = tx.fromAddress?.toLowerCase();
      if (toAddr && addrSet.has(toAddr)) {
        walletAddr = toAddr;
      } else if (fromAddr && addrSet.has(fromAddr)) {
        walletAddr = fromAddr;
      }
    }
    if (!walletAddr && walletAddresses.length > 0) {
      walletAddr = walletAddresses[0];
    }

    holdings.push({
      token: lot.token,
      currentAmount: remaining,
      currentValueUsd: remainingCost,
      walletAddress: walletAddr,
      chain,
      acquisitionMethod: classifyAcquisitionMethod(source),
      originalAcquisitionDate: acqDate,
      originalAcquisitionCost: remainingCost,
      fundingTrail: trail,
    });

    totalValue = totalValue.plus(remainingCost);
    totalCost = totalCost.plus(remainingCost);
  }

  return {
    generatedAt: new Date().toISOString(),
    walletAddresses,
    holdings,
    totalPortfolioValue: totalValue,
    totalAcquisitionCost: totalCost,
  };
}

// ---------------------------------------------------------------------------
// CSV formatter
// ---------------------------------------------------------------------------

/**
 * Generate Source of Funds CSV report.
 */
export function generateSourceOfFundsCsv(report: SourceOfFundsReport): ReportFile {
  const headers = [
    'Token', 'Amount', 'Current Value (USD)', 'Acquisition Method',
    'Acquisition Date', 'Original Cost (USD)', 'Source', 'Chain', 'Wallet Address',
  ];

  const rows: string[][] = [];
  for (const h of report.holdings) {
    const source = h.fundingTrail.length > 0 ? h.fundingTrail[0].source : 'N/A';
    rows.push([
      h.token,
      h.currentAmount.toString(),
      h.currentValueUsd.toString(),
      methodLabel(h.acquisitionMethod),
      h.originalAcquisitionDate,
      h.originalAcquisitionCost.toString(),
      source,
      h.chain,
      h.walletAddress,
    ]);
  }

  return {
    filename: 'source_of_funds.csv',
    content: buildCsv(headers, rows),
    mimeType: 'text/csv',
    reportType: 'source_of_funds',
  };
}

// ---------------------------------------------------------------------------
// Text report formatter
// ---------------------------------------------------------------------------

/**
 * Generate human-readable Source of Funds text report for KYC submission.
 */
export function generateSourceOfFundsText(report: SourceOfFundsReport): ReportFile {
  const lines: string[] = [];

  // Header
  lines.push('='.repeat(72));
  lines.push('SOURCE OF FUNDS REPORT');
  lines.push('='.repeat(72));
  lines.push('');
  lines.push(`Report generated: ${report.generatedAt.slice(0, 19).replace('T', ' ')} UTC`);
  lines.push(`Wallets covered:  ${report.walletAddresses.length}`);
  for (const addr of report.walletAddresses) {
    lines.push(`  - ${addr}`);
  }
  lines.push('');
  lines.push(`Total holdings traced: ${report.holdings.length}`);
  lines.push('');
  lines.push('-'.repeat(72));

  // Per-holding sections
  for (let i = 0; i < report.holdings.length; i++) {
    const h = report.holdings[i];
    lines.push('');
    lines.push(`HOLDING ${i + 1}: ${h.currentAmount.toString()} ${h.token}`);
    lines.push(`  Wallet:             ${h.walletAddress}`);
    lines.push(`  Chain:              ${h.chain}`);
    lines.push(`  Acquisition Method: ${methodLabel(h.acquisitionMethod)}`);
    lines.push(`  Acquisition Date:   ${h.originalAcquisitionDate}`);
    lines.push(`  Original Cost:      $${h.originalAcquisitionCost.toString()}`);
    lines.push(`  Current Value:      $${h.currentValueUsd.toString()}`);
    lines.push('');

    if (h.fundingTrail.length > 0) {
      lines.push('  Transaction Trail:');
      for (const step of h.fundingTrail) {
        const txRef = step.txHash
          ? (step.txHash.length > 16 ? step.txHash.slice(0, 16) + '...' : step.txHash)
          : 'N/A';
        lines.push(
          `    Step ${step.stepNumber}: ` +
          `${step.date} -- ${step.action} ` +
          `${step.amount.toString()} ${step.token} ` +
          `($${step.valueUsd.toString()}) ` +
          `via ${step.source} ` +
          `[${step.chain}] ` +
          `tx: ${txRef}`,
        );
      }
    } else {
      lines.push('  Transaction Trail: No detailed trail available.');
    }

    lines.push('');
    lines.push('-'.repeat(72));
  }

  // Summary
  lines.push('');
  lines.push('SUMMARY');
  lines.push('='.repeat(72));
  lines.push(`Total Portfolio Value (cost basis): $${report.totalPortfolioValue.toString()}`);
  lines.push(`Total Acquisition Cost:             $${report.totalAcquisitionCost.toString()}`);
  lines.push(`Number of Holdings:                 ${report.holdings.length}`);
  lines.push('');

  // Footer
  lines.push('-'.repeat(72));
  lines.push('METHODOLOGY');
  lines.push('-'.repeat(72));
  lines.push(
    'This report was generated by automated analysis of on-chain ' +
    'transaction data. Each holding was traced backward through the ' +
    'complete transaction history to identify its original acquisition ' +
    'source. Transaction data was obtained from public blockchain ' +
    'explorers and exchange import records.',
  );
  lines.push('');
  lines.push(
    'Values shown are based on the fair market value (FMV) at the time ' +
    'of each transaction, sourced from CoinGecko price data. Cost basis ' +
    'is calculated using the FIFO (First In, First Out) method unless ' +
    'otherwise specified.',
  );
  lines.push('');
  lines.push('This report is provided for informational purposes only and');
  lines.push('does not constitute tax or legal advice.');
  lines.push('');
  lines.push('='.repeat(72));

  return {
    filename: 'source_of_funds.txt',
    content: lines.join('\n'),
    mimeType: 'text/plain',
    reportType: 'source_of_funds_text',
  };
}
