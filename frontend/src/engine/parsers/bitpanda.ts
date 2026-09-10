/**
 * Bitpanda CSV parser.
 *
 * Ported from src/importers/exchange.py _parse_bitpanda method.
 *
 * Expected columns:
 *   Transaction ID, Timestamp, Transaction Type, In/Out, Amount Fiat,
 *   Fiat, Amount Asset, Asset, Asset market price, Asset market price currency,
 *   Asset class, Product ID, Fee, Fee asset, Spread, Spread Currency, Status
 *
 * Filters crypto-only rows (Bitpanda also handles stocks, metals, indices).
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
 * Parse Bitpanda CSV rows into Transaction objects.
 *
 * @param rows - Array of parsed CSV row objects (from PapaParse)
 * @returns Array of Transaction objects sorted by timestamp
 */
export function parseBitpandaCsv(
  rows: Record<string, string>[],
): Transaction[] {
  const transactions: Transaction[] = [];

  for (const row of rows) {
    try {
      const assetClass = (row['Asset class'] ?? '').trim().toLowerCase();
      if (assetClass && !['cryptocurrency', 'crypto'].includes(assetClass)) continue;

      const status = (row['Status'] ?? '').trim().toLowerCase();
      if (status && !['finished', 'completed', 'confirmed', ''].includes(status)) continue;

      const timestampStr = (row['Timestamp'] ?? '').trim();
      const txTypeRaw = (row['Transaction Type'] ?? '').trim().toLowerCase();
      const direction = (row['In/Out'] ?? '').trim().toLowerCase();
      const asset = (row['Asset'] ?? '').trim();
      const amount = parseDecimal(row['Amount Asset']);
      const fiatAmount = parseDecimal(row['Amount Fiat']);
      const fiatCurrency = (row['Fiat'] ?? 'EUR').trim();
      const feeVal = parseDecimal(row['Fee']);
      const feeAsset = (row['Fee asset'] ?? fiatCurrency).trim();

      if (!timestampStr || !asset || amount.isZero()) continue;

      const timestamp = timestampStr.replace('Z', '+00:00');

      const assetsIn: Array<{ tokenSymbol: string; amount: Decimal }> = [];
      const assetsOut: Array<{ tokenSymbol: string; amount: Decimal }> = [];
      let fee: { tokenSymbol: string; amount: Decimal } | null = null;

      if (feeVal.gt('0')) {
        fee = { tokenSymbol: feeAsset, amount: feeVal };
      }

      if (direction === 'incoming' || ['buy', 'deposit', 'reward'].includes(txTypeRaw)) {
        assetsIn.push({ tokenSymbol: asset, amount });
        if (txTypeRaw === 'buy' && fiatAmount.gt('0')) {
          assetsOut.push({ tokenSymbol: fiatCurrency, amount: fiatAmount });
        }
      } else if (direction === 'outgoing' || ['sell', 'withdrawal'].includes(txTypeRaw)) {
        assetsOut.push({ tokenSymbol: asset, amount });
        if (txTypeRaw === 'sell' && fiatAmount.gt('0')) {
          assetsIn.push({ tokenSymbol: fiatCurrency, amount: fiatAmount });
        }
      } else {
        continue;
      }

      const normalizedType: Record<string, string> = {
        buy: 'swap', sell: 'swap', deposit: 'transfer',
        withdrawal: 'transfer', transfer: 'transfer', reward: 'reward',
      };

      const txId = row['Transaction ID'] ?? `bitpanda_${uniqueId()}`;

      transactions.push(
        createTransaction({
          txHash: `bitpanda_${txId}`,
          chain: 'bitpanda',
          blockNumber: 0,
          timestamp,
          fromAddress: 'bitpanda',
          toAddress: 'wallet',
          txType: normalizedType[txTypeRaw] ?? 'unknown',
          assetsIn,
          assetsOut,
          fee,
          protocol: 'Bitpanda',
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
