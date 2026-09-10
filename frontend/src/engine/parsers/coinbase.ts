/**
 * Coinbase CSV parser.
 *
 * Ported from src/importers/exchange.py _parse_coinbase method.
 *
 * Expected columns:
 *   Timestamp, Transaction Type, Asset, Quantity Transacted,
 *   Spot Price Currency, Spot Price at Transaction, Subtotal,
 *   Total (inclusive of fees and/or spread), Fees and/or Spread, Notes
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Transaction } from '../types';
import { createTransaction, createAssetTransfer } from '../types';

function parseDecimal(value: string | undefined): Decimal {
  if (!value) return new Decimal('0');
  const cleaned = value.trim().replace(/,/g, '').replace(/^[$\u20ac\u00a3]/, '');
  try {
    return cleaned ? new Decimal(cleaned) : new Decimal('0');
  } catch {
    return new Decimal('0');
  }
}

function coinbaseTypeToTxType(coinbaseType: string): string {
  const map: Record<string, string> = {
    buy: 'swap',
    sell: 'swap',
    send: 'transfer',
    receive: 'transfer',
    convert: 'swap',
    'coinbase earn': 'airdrop',
    'rewards income': 'reward',
    'learning reward': 'airdrop',
  };
  return map[coinbaseType] ?? 'unknown';
}

let _counter = 0;
function uniqueId(): string {
  return String(++_counter).padStart(8, '0');
}

/**
 * Parse Coinbase transaction history CSV rows into Transaction objects.
 *
 * @param rows - Array of parsed CSV row objects (from PapaParse)
 * @returns Array of Transaction objects sorted by timestamp
 */
export function parseCoinbaseCsv(
  rows: Record<string, string>[],
): Transaction[] {
  const transactions: Transaction[] = [];

  for (const row of rows) {
    try {
      const txTypeRaw = (row['Transaction Type'] ?? '').trim().toLowerCase();
      const asset = (row['Asset'] ?? '').trim();
      const quantity = parseDecimal(row['Quantity Transacted']);
      const total = parseDecimal(row['Total (inclusive of fees and/or spread)']);
      const fees = parseDecimal(row['Fees and/or Spread']);
      const spotCurrency = (row['Spot Price Currency'] ?? 'USD').trim();
      const timestampStr = (row['Timestamp'] ?? '').trim();

      if (!timestampStr || !asset || quantity.isZero()) continue;

      const timestamp = timestampStr.replace('Z', '+00:00');
      const usdValue = spotCurrency === 'USD' ? total.abs() : null;
      const feeUsd = spotCurrency === 'USD' ? fees : new Decimal('0');

      const assetsIn: Array<{
        tokenSymbol: string;
        amount: Decimal;
        usdValue?: Decimal | null;
      }> = [];
      const assetsOut: Array<{
        tokenSymbol: string;
        amount: Decimal;
        usdValue?: Decimal | null;
      }> = [];
      let fee: { tokenSymbol: string; amount: Decimal; usdValue?: Decimal | null } | null = null;

      if (feeUsd.gt('0')) {
        fee = { tokenSymbol: 'USD', amount: feeUsd, usdValue: feeUsd };
      }

      if (['buy', 'receive', 'coinbase earn', 'rewards income', 'learning reward'].includes(txTypeRaw)) {
        assetsIn.push({ tokenSymbol: asset, amount: quantity, usdValue });
        if (txTypeRaw === 'buy') {
          assetsOut.push({ tokenSymbol: spotCurrency, amount: total.abs(), usdValue });
        }
      } else if (['sell', 'send'].includes(txTypeRaw)) {
        assetsOut.push({ tokenSymbol: asset, amount: quantity, usdValue });
        if (txTypeRaw === 'sell') {
          const netProceeds = total.abs().minus(feeUsd);
          assetsIn.push({
            tokenSymbol: spotCurrency,
            amount: netProceeds,
            usdValue: spotCurrency === 'USD' ? netProceeds : null,
          });
        }
      } else if (txTypeRaw === 'convert') {
        assetsOut.push({ tokenSymbol: asset, amount: quantity, usdValue });
      } else {
        continue;
      }

      transactions.push(
        createTransaction({
          txHash: `coinbase_${txTypeRaw}_${asset}_${timestamp}_${uniqueId()}`,
          chain: 'coinbase',
          blockNumber: 0,
          timestamp,
          fromAddress: 'coinbase',
          toAddress: 'wallet',
          txType: coinbaseTypeToTxType(txTypeRaw),
          assetsIn,
          assetsOut,
          fee,
          protocol: 'Coinbase',
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
