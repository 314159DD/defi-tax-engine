/**
 * Binance CSV parser.
 *
 * Ported from src/importers/exchange.py _parse_binance method.
 *
 * Expected columns:
 *   Date(UTC), Pair, Side, Price, Executed, Amount, Fee
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

/** Split "0.5ETH" into [Decimal("0.5"), "ETH"]. */
function splitAmountSymbol(raw: string): [Decimal, string] {
  const trimmed = raw.trim();
  const match = trimmed.match(/^([0-9.,]+)\s*([A-Za-z]+)$/);
  if (match) {
    return [parseDecimal(match[1]), match[2].toUpperCase()];
  }
  return [parseDecimal(trimmed), ''];
}

let _counter = 0;
function uniqueId(): string {
  return String(++_counter).padStart(8, '0');
}

/**
 * Parse Binance trade history CSV rows into Transaction objects.
 *
 * @param rows - Array of parsed CSV row objects (from PapaParse)
 * @returns Array of Transaction objects sorted by timestamp
 */
export function parseBinanceCsv(
  rows: Record<string, string>[],
): Transaction[] {
  const transactions: Transaction[] = [];

  for (const row of rows) {
    try {
      const dateStr = (row['Date(UTC)'] ?? '').trim();
      const pair = (row['Pair'] ?? '').trim();
      const side = (row['Side'] ?? '').trim().toLowerCase();
      const price = parseDecimal(row['Price']);
      const executedRaw = (row['Executed'] ?? '0').trim();
      const amountRaw = (row['Amount'] ?? '0').trim();
      const feeRaw = (row['Fee'] ?? '0').trim();

      if (!dateStr || !pair) continue;

      // Parse "YYYY-MM-DD HH:MM:SS" to ISO
      const timestamp = dateStr.replace(' ', 'T') + 'Z';

      const [executedQty, executedSymbol] = splitAmountSymbol(executedRaw);
      const [amountQty, amountSymbol] = splitAmountSymbol(amountRaw);
      const [feeQty, feeSymbol] = splitAmountSymbol(feeRaw);

      const usdValue = price.gt('0') ? price.times(executedQty) : null;

      const assetsIn: Array<{ tokenSymbol: string; amount: Decimal; usdValue?: Decimal | null }> = [];
      const assetsOut: Array<{ tokenSymbol: string; amount: Decimal; usdValue?: Decimal | null }> = [];

      if (side === 'buy') {
        assetsIn.push({ tokenSymbol: executedSymbol, amount: executedQty, usdValue });
        assetsOut.push({ tokenSymbol: amountSymbol, amount: amountQty, usdValue });
      } else {
        assetsOut.push({ tokenSymbol: executedSymbol, amount: executedQty, usdValue });
        assetsIn.push({ tokenSymbol: amountSymbol, amount: amountQty, usdValue });
      }

      let fee: { tokenSymbol: string; amount: Decimal } | null = null;
      if (feeQty.gt('0')) {
        fee = { tokenSymbol: feeSymbol, amount: feeQty };
      }

      transactions.push(
        createTransaction({
          txHash: `binance_${pair}_${side}_${dateStr}_${uniqueId()}`,
          chain: 'binance',
          blockNumber: 0,
          timestamp,
          fromAddress: 'binance',
          toAddress: 'wallet',
          txType: 'swap',
          assetsIn,
          assetsOut,
          fee,
          protocol: 'Binance',
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
