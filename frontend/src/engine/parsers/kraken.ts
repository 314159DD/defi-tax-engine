/**
 * Kraken CSV parser.
 *
 * Ported from src/importers/exchange.py _parse_kraken method.
 *
 * Expected columns (Kraken ledger):
 *   txid, refid, time, type, subtype, aclass, asset, amount, fee, balance
 *
 * Trades have two rows per refid (buy side + sell side).
 * Deposits/withdrawals/staking are single rows.
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Transaction } from '../types';
import { createTransaction } from '../types';

function parseDecimal(value: string | undefined): Decimal {
  if (!value) return new Decimal('0');
  const cleaned = value.trim().replace(/,/g, '');
  try {
    return cleaned ? new Decimal(cleaned) : new Decimal('0');
  } catch {
    return new Decimal('0');
  }
}

const KRAKEN_ASSET_MAP: Record<string, string> = {
  XETH: 'ETH', XXBT: 'BTC', XLTC: 'LTC', XXRP: 'XRP',
  XXLM: 'XLM', XXDG: 'DOGE', ZUSD: 'USD', ZEUR: 'EUR', ZGBP: 'GBP',
};

function normalizeKrakenAsset(asset: string): string {
  const upper = asset.toUpperCase();
  if (KRAKEN_ASSET_MAP[upper]) return KRAKEN_ASSET_MAP[upper];
  // Strip leading X or Z if longer than 3 chars
  if (upper.length > 3 && (upper.startsWith('X') || upper.startsWith('Z'))) {
    return upper.slice(1);
  }
  return upper;
}

let _counter = 0;
function uniqueId(): string {
  return String(++_counter).padStart(8, '0');
}

function krakenTradePair(
  rowA: Record<string, string>,
  rowB: Record<string, string>,
): Transaction | null {
  const timeStr = (rowA['time'] ?? '').trim();
  const timestamp = timeStr.replace(' ', 'T') + 'Z';

  const assetsIn: Array<{ tokenSymbol: string; amount: Decimal }> = [];
  const assetsOut: Array<{ tokenSymbol: string; amount: Decimal }> = [];
  let fee: { tokenSymbol: string; amount: Decimal } | null = null;

  for (const row of [rowA, rowB]) {
    const amount = parseDecimal(row['amount']);
    const feeVal = parseDecimal(row['fee']);
    const asset = normalizeKrakenAsset(row['asset'] ?? '');

    if (feeVal.gt('0')) {
      fee = { tokenSymbol: asset, amount: feeVal };
    }

    if (amount.gt('0')) {
      assetsIn.push({ tokenSymbol: asset, amount });
    } else if (amount.lt('0')) {
      assetsOut.push({ tokenSymbol: asset, amount: amount.abs() });
    }
  }

  return createTransaction({
    txHash: `kraken_${rowA['refid'] ?? ''}_${uniqueId()}`,
    chain: 'kraken',
    blockNumber: 0,
    timestamp,
    fromAddress: 'kraken',
    toAddress: 'wallet',
    txType: 'swap',
    assetsIn,
    assetsOut,
    fee,
    protocol: 'Kraken',
    rawData: { rows: [rowA, rowB] },
  });
}

function krakenSingleRow(row: Record<string, string>): Transaction | null {
  const txTypeRaw = (row['type'] ?? '').trim().toLowerCase();
  if (!['deposit', 'withdrawal', 'staking', 'earn'].includes(txTypeRaw)) return null;

  const timeStr = (row['time'] ?? '').trim();
  const timestamp = timeStr.replace(' ', 'T') + 'Z';
  const amount = parseDecimal(row['amount']);
  const asset = normalizeKrakenAsset(row['asset'] ?? '');

  if (amount.isZero()) return null;

  const assetsIn: Array<{ tokenSymbol: string; amount: Decimal }> = [];
  const assetsOut: Array<{ tokenSymbol: string; amount: Decimal }> = [];

  if (['deposit', 'staking', 'earn'].includes(txTypeRaw)) {
    assetsIn.push({ tokenSymbol: asset, amount: amount.abs() });
  } else {
    assetsOut.push({ tokenSymbol: asset, amount: amount.abs() });
  }

  const normalizedType: Record<string, string> = {
    deposit: 'transfer', withdrawal: 'transfer', staking: 'reward', earn: 'reward',
  };

  return createTransaction({
    txHash: `kraken_${row['txid'] ?? ''}_${uniqueId()}`,
    chain: 'kraken',
    blockNumber: 0,
    timestamp,
    fromAddress: 'kraken',
    toAddress: 'wallet',
    txType: normalizedType[txTypeRaw] ?? 'unknown',
    assetsIn,
    assetsOut,
    fee: null,
    protocol: 'Kraken',
    rawData: { ...row },
  });
}

/**
 * Parse Kraken ledger CSV rows into Transaction objects.
 *
 * @param rows - Array of parsed CSV row objects (from PapaParse)
 * @returns Array of Transaction objects sorted by timestamp
 */
export function parseKrakenCsv(
  rows: Record<string, string>[],
): Transaction[] {
  const transactions: Transaction[] = [];

  // Group rows by refid
  const rowsByRefid = new Map<string, Record<string, string>[]>();
  for (const row of rows) {
    const refid = (row['refid'] ?? '').trim();
    if (!refid) continue;
    if (!rowsByRefid.has(refid)) rowsByRefid.set(refid, []);
    rowsByRefid.get(refid)!.push(row);
  }

  rowsByRefid.forEach((refRows) => {
    try {
      let tx: Transaction | null = null;
      if (refRows.length === 2) {
        tx = krakenTradePair(refRows[0], refRows[1]);
      } else if (refRows.length === 1) {
        tx = krakenSingleRow(refRows[0]);
      }
      if (tx) transactions.push(tx);
    } catch {
      // Skip unparseable groups
    }
  });

  return transactions.sort(
    (a, b) => a.timestamp.localeCompare(b.timestamp),
  );
}
