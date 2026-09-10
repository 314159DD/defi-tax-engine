/**
 * Bison CSV parser (German -- Boerse Stuttgart).
 *
 * Ported from src/importers/exchange.py _parse_bison method.
 *
 * Expected columns (semicolon-delimited, German headers):
 *   Datum, Typ, Kryptowaehrung, Menge, Kurs, EUR-Betrag, Gebuehr
 *   (Date, Type, Cryptocurrency, Amount, Price, EUR Amount, Fee)
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Transaction } from '../types';
import { createTransaction } from '../types';

function parseDecimal(value: string | undefined): Decimal {
  if (!value) return new Decimal('0');
  // German decimals may use comma as decimal separator
  const cleaned = value.trim().replace(/\./g, '').replace(',', '.');
  try {
    return cleaned ? new Decimal(cleaned) : new Decimal('0');
  } catch {
    return new Decimal('0');
  }
}

/** Parse German date formats to ISO timestamp. */
function parseDateToISO(dateStr: string): string | null {
  // Try DD.MM.YYYY HH:MM:SS
  let match = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})$/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]}T${match[4]}:${match[5]}:${match[6]}Z`;
  }
  // Try DD.MM.YYYY HH:MM
  match = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})$/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]}T${match[4]}:${match[5]}:00Z`;
  }
  // Try DD.MM.YYYY
  match = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]}T00:00:00Z`;
  }
  // Try YYYY-MM-DD HH:MM:SS
  match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/);
  if (match) {
    return `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${match[6]}Z`;
  }
  return null;
}

let _counter = 0;
function uniqueId(): string {
  return String(++_counter).padStart(8, '0');
}

/**
 * Parse Bison CSV rows into Transaction objects.
 *
 * NOTE: Bison uses semicolon delimiter -- PapaParse must be configured
 * with delimiter: ';' when parsing the raw CSV text.
 *
 * @param rows - Array of parsed CSV row objects (from PapaParse with delimiter=';')
 * @returns Array of Transaction objects sorted by timestamp
 */
export function parseBisonCsv(
  rows: Record<string, string>[],
): Transaction[] {
  const transactions: Transaction[] = [];

  for (const row of rows) {
    try {
      const dateStr = (row['Datum'] ?? row['Date'] ?? '').trim();
      const txTypeRaw = (row['Typ'] ?? row['Type'] ?? '').trim().toLowerCase();
      const asset = (row['Kryptow\u00e4hrung'] ?? row['Cryptocurrency'] ?? '').trim();
      const amount = parseDecimal(row['Menge'] ?? row['Amount']);
      const eurAmount = parseDecimal(row['EUR-Betrag'] ?? row['EUR Amount']);
      const feeVal = parseDecimal(row['Geb\u00fchr'] ?? row['Fee']);

      if (!dateStr || !asset || amount.isZero()) continue;

      const timestamp = parseDateToISO(dateStr);
      if (!timestamp) continue;

      const assetsIn: Array<{ tokenSymbol: string; amount: Decimal }> = [];
      const assetsOut: Array<{ tokenSymbol: string; amount: Decimal }> = [];
      let fee: { tokenSymbol: string; amount: Decimal } | null = null;
      let normalizedType: string;

      if (feeVal.gt('0')) {
        fee = { tokenSymbol: 'EUR', amount: feeVal };
      }

      if (['kauf', 'buy'].includes(txTypeRaw)) {
        assetsIn.push({ tokenSymbol: asset, amount });
        if (eurAmount.gt('0')) {
          assetsOut.push({ tokenSymbol: 'EUR', amount: eurAmount.abs() });
        }
        normalizedType = 'swap';
      } else if (['verkauf', 'sell'].includes(txTypeRaw)) {
        assetsOut.push({ tokenSymbol: asset, amount });
        if (eurAmount.gt('0')) {
          assetsIn.push({ tokenSymbol: 'EUR', amount: eurAmount.abs() });
        }
        normalizedType = 'swap';
      } else if (['einzahlung', 'deposit', 'empfang', 'receive'].includes(txTypeRaw)) {
        assetsIn.push({ tokenSymbol: asset, amount });
        normalizedType = 'transfer';
      } else if (['auszahlung', 'withdrawal', 'senden', 'send'].includes(txTypeRaw)) {
        assetsOut.push({ tokenSymbol: asset, amount });
        normalizedType = 'transfer';
      } else {
        continue;
      }

      transactions.push(
        createTransaction({
          txHash: `bison_${asset}_${dateStr}_${uniqueId()}`,
          chain: 'bison',
          blockNumber: 0,
          timestamp,
          fromAddress: 'bison',
          toAddress: 'wallet',
          txType: normalizedType,
          assetsIn,
          assetsOut,
          fee,
          protocol: 'Bison',
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
