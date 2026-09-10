/**
 * Trade Republic CSV parser (German neobroker -- crypto subset).
 *
 * Ported from src/importers/exchange.py _parse_trade_republic method.
 *
 * Expected columns (semicolon-delimited, German headers):
 *   Datum, Typ, ISIN, Name, Stueck, Kurs, Betrag, Gebuehren
 *   (Date, Type, ISIN, Name, Shares/Amount, Price, Total, Fees)
 *
 * Note: Crypto rows have no ISIN (or crypto-specific identifier).
 * Rows with a 12-char ISIN are stocks/ETFs and get skipped.
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
  let match = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})$/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]}T${match[4]}:${match[5]}:${match[6]}Z`;
  }
  match = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})$/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]}T${match[4]}:${match[5]}:00Z`;
  }
  match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/);
  if (match) {
    return `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${match[6]}Z`;
  }
  match = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]}T00:00:00Z`;
  }
  return null;
}

const CRYPTO_KEYWORDS = new Set([
  'bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'cardano', 'ada',
  'polygon', 'matic', 'polkadot', 'dot', 'chainlink', 'link', 'avalanche',
  'avax', 'litecoin', 'ltc', 'uniswap', 'uni', 'dogecoin', 'doge', 'shiba',
  'shib', 'ripple', 'xrp',
]);

const SYMBOL_MAP: Record<string, string> = {
  bitcoin: 'BTC', ethereum: 'ETH', solana: 'SOL', cardano: 'ADA',
  polygon: 'MATIC', polkadot: 'DOT', chainlink: 'LINK', avalanche: 'AVAX',
  litecoin: 'LTC', uniswap: 'UNI', dogecoin: 'DOGE', shiba: 'SHIB',
  ripple: 'XRP',
};

function extractCryptoSymbol(name: string): string {
  const lower = name.toLowerCase();
  for (const [keyword, symbol] of Object.entries(SYMBOL_MAP)) {
    if (lower.includes(keyword)) return symbol;
  }
  return name.split(/\s+/)[0]?.toUpperCase() ?? 'UNKNOWN';
}

let _counter = 0;
function uniqueId(): string {
  return String(++_counter).padStart(8, '0');
}

/**
 * Parse Trade Republic CSV rows into Transaction objects.
 *
 * NOTE: Trade Republic uses semicolon delimiter -- PapaParse must be configured
 * with delimiter: ';' when parsing the raw CSV text.
 *
 * @param rows - Array of parsed CSV row objects (from PapaParse with delimiter=';')
 * @returns Array of Transaction objects sorted by timestamp
 */
export function parseTradeRepublicCsv(
  rows: Record<string, string>[],
): Transaction[] {
  const transactions: Transaction[] = [];

  for (const row of rows) {
    try {
      const dateStr = (row['Datum'] ?? row['Date'] ?? '').trim();
      const txTypeRaw = (row['Typ'] ?? row['Type'] ?? '').trim().toLowerCase();
      const name = (row['Name'] ?? '').trim();
      const isin = (row['ISIN'] ?? '').trim();
      const amount = parseDecimal(row['St\u00fcck'] ?? row['Shares'] ?? row['Amount']);
      const total = parseDecimal(row['Betrag'] ?? row['Total']);
      const feeVal = parseDecimal(row['Geb\u00fchren'] ?? row['Fees']);

      if (!dateStr || amount.isZero()) continue;

      // Skip stocks/ETFs (they have 12-char ISINs)
      if (isin && isin.length === 12) continue;

      // Check if name matches known crypto
      const nameLower = name.toLowerCase();
      const isCrypto = Array.from(CRYPTO_KEYWORDS).some((kw) => nameLower.includes(kw));
      if (!isCrypto) continue;

      const asset = extractCryptoSymbol(name);

      const timestamp = parseDateToISO(dateStr);
      if (!timestamp) continue;

      const assetsIn: Array<{ tokenSymbol: string; amount: Decimal }> = [];
      const assetsOut: Array<{ tokenSymbol: string; amount: Decimal }> = [];
      let fee: { tokenSymbol: string; amount: Decimal } | null = null;
      let normalizedType: string;

      if (feeVal.gt('0')) {
        fee = { tokenSymbol: 'EUR', amount: feeVal.abs() };
      }

      if (['kauf', 'buy', 'sparplan', 'savings plan'].includes(txTypeRaw)) {
        assetsIn.push({ tokenSymbol: asset, amount });
        if (!total.isZero()) {
          assetsOut.push({ tokenSymbol: 'EUR', amount: total.abs() });
        }
        normalizedType = 'swap';
      } else if (['verkauf', 'sell'].includes(txTypeRaw)) {
        assetsOut.push({ tokenSymbol: asset, amount });
        if (!total.isZero()) {
          assetsIn.push({ tokenSymbol: 'EUR', amount: total.abs() });
        }
        normalizedType = 'swap';
      } else {
        continue;
      }

      transactions.push(
        createTransaction({
          txHash: `trade_republic_${asset}_${dateStr}_${uniqueId()}`,
          chain: 'trade_republic',
          blockNumber: 0,
          timestamp,
          fromAddress: 'trade_republic',
          toAddress: 'wallet',
          txType: normalizedType,
          assetsIn,
          assetsOut,
          fee,
          protocol: 'Trade Republic',
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
