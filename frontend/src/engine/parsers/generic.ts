/**
 * Generic CSV parser with user-provided column mapping.
 *
 * Ported from src/importers/exchange.py _parse_generic method.
 *
 * Allows users to import CSV from any exchange by mapping their column names
 * to our standard fields.
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Transaction } from '../types';
import { createTransaction } from '../types';

function parseDecimal(value: string | undefined): Decimal {
  if (!value) return new Decimal('0');
  const cleaned = value.trim().replace(/,/g, '').replace(/^[$\u20ac\u00a3]/, '');
  try {
    return cleaned ? new Decimal(cleaned) : new Decimal('0');
  } catch {
    return new Decimal('0');
  }
}

let _counter = 0;
function uniqueId(): string {
  return String(++_counter).padStart(8, '0');
}

/**
 * Column mapping from our standard field names to the actual CSV column headers.
 *
 * Required: timestamp, type, asset, amount
 * Optional: fiatAmount, fiatCurrency, fee, feeAsset, txHash
 */
export interface ColumnMapping {
  timestamp: string;    // Column name for date/time
  type: string;         // Column name for tx type (buy/sell/send/receive/reward)
  asset: string;        // Column name for crypto asset
  amount: string;       // Column name for crypto amount
  fiatAmount?: string;  // Column name for fiat amount
  fiatCurrency?: string; // Column name for fiat currency (or static value)
  fee?: string;         // Column name for fee amount
  feeAsset?: string;    // Column name for fee asset symbol
  txHash?: string;      // Column name for tx hash / reference ID
  exchange?: string;    // Static exchange name
}

/**
 * Parse generic CSV rows into Transaction objects using a user-provided column mapping.
 *
 * @param rows          - Array of parsed CSV row objects (from PapaParse)
 * @param columnMapping - Maps our field names to actual CSV column names
 * @returns Array of Transaction objects sorted by timestamp
 */
export function parseGenericCsv(
  rows: Record<string, string>[],
  columnMapping: ColumnMapping,
): Transaction[] {
  const transactions: Transaction[] = [];
  const exchange = columnMapping.exchange ?? 'generic';

  for (const row of rows) {
    try {
      const timestampStr = (row[columnMapping.timestamp] ?? '').trim();
      const txTypeRaw = (row[columnMapping.type] ?? '').trim().toLowerCase();
      const asset = (row[columnMapping.asset] ?? '').trim().toUpperCase();
      const amount = parseDecimal(row[columnMapping.amount]);

      if (!timestampStr || !asset || amount.isZero()) continue;

      // Normalize timestamp to ISO
      let timestamp: string;
      try {
        const d = new Date(timestampStr);
        if (isNaN(d.getTime())) continue;
        timestamp = d.toISOString();
      } catch {
        continue;
      }

      const fiatAmount = columnMapping.fiatAmount
        ? parseDecimal(row[columnMapping.fiatAmount])
        : new Decimal('0');
      const fiatCurrency = columnMapping.fiatCurrency
        ? (row[columnMapping.fiatCurrency]?.trim().toUpperCase() ?? 'USD')
        : 'USD';
      const feeVal = columnMapping.fee
        ? parseDecimal(row[columnMapping.fee])
        : new Decimal('0');
      const feeAsset = columnMapping.feeAsset
        ? (row[columnMapping.feeAsset]?.trim().toUpperCase() ?? fiatCurrency)
        : fiatCurrency;
      const txHash = columnMapping.txHash
        ? (row[columnMapping.txHash]?.trim() ?? '')
        : '';

      const assetsIn: Array<{ tokenSymbol: string; amount: Decimal }> = [];
      const assetsOut: Array<{ tokenSymbol: string; amount: Decimal }> = [];
      let fee: { tokenSymbol: string; amount: Decimal } | null = null;
      let normalizedType: string;

      if (feeVal.gt('0')) {
        fee = { tokenSymbol: feeAsset, amount: feeVal };
      }

      if (['buy', 'purchase', 'receive', 'deposit'].includes(txTypeRaw)) {
        assetsIn.push({ tokenSymbol: asset, amount });
        if (fiatAmount.gt('0') && ['buy', 'purchase'].includes(txTypeRaw)) {
          assetsOut.push({ tokenSymbol: fiatCurrency, amount: fiatAmount });
        }
        normalizedType = ['buy', 'purchase'].includes(txTypeRaw) ? 'swap' : 'transfer';
      } else if (['sell', 'send', 'withdrawal'].includes(txTypeRaw)) {
        assetsOut.push({ tokenSymbol: asset, amount });
        if (fiatAmount.gt('0') && txTypeRaw === 'sell') {
          assetsIn.push({ tokenSymbol: fiatCurrency, amount: fiatAmount });
        }
        normalizedType = txTypeRaw === 'sell' ? 'swap' : 'transfer';
      } else if (['reward', 'staking', 'earn', 'interest'].includes(txTypeRaw)) {
        assetsIn.push({ tokenSymbol: asset, amount });
        normalizedType = 'reward';
      } else if (['airdrop'].includes(txTypeRaw)) {
        assetsIn.push({ tokenSymbol: asset, amount });
        normalizedType = 'airdrop';
      } else if (['swap', 'trade', 'convert', 'exchange'].includes(txTypeRaw)) {
        assetsOut.push({ tokenSymbol: asset, amount });
        normalizedType = 'swap';
      } else {
        // Default: treat as transfer in
        assetsIn.push({ tokenSymbol: asset, amount });
        normalizedType = 'unknown';
      }

      const hash = txHash || `${exchange}_${asset}_${timestampStr}_${uniqueId()}`;

      transactions.push(
        createTransaction({
          txHash: hash,
          chain: exchange,
          blockNumber: 0,
          timestamp,
          fromAddress: exchange,
          toAddress: 'wallet',
          txType: normalizedType,
          assetsIn,
          assetsOut,
          fee,
          protocol: exchange.charAt(0).toUpperCase() + exchange.slice(1),
          rawData: { ...row },
        }),
      );
    } catch {
      // Skip unparseable rows
    }
  }

  return transactions.sort(
    (a, b) => a.timestamp.localeCompare(b.timestamp),
  );
}
