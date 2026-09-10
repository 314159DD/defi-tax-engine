/**
 * CEX CSV parser orchestrator -- detects format and parses.
 *
 * Ported from src/importers/exchange.py ExchangeImporter.
 *
 * All parsing runs entirely client-side using PapaParse.
 *
 * Supported formats:
 *   coinbase, binance, kraken, bitpanda, bison, trade_republic, generic
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import * as Papa from 'papaparse';
import type { Transaction } from '../types';
import { parseCoinbaseCsv } from './coinbase';
import { parseBinanceCsv } from './binance';
import { parseKrakenCsv } from './kraken';
import { parseBitpandaCsv } from './bitpanda';
import { parseBisonCsv } from './bison';
import { parseTradeRepublicCsv } from './trade-republic';
import { parseGenericCsv, type ColumnMapping } from './generic';

export type ExchangeFormat =
  | 'coinbase'
  | 'binance'
  | 'kraken'
  | 'bitpanda'
  | 'bison'
  | 'trade_republic'
  | 'generic'
  | 'unknown';

// ---------------------------------------------------------------------------
// Header signature detection
// ---------------------------------------------------------------------------

// Coinbase transaction history
const COINBASE_SIGNATURES = [
  'transaction type', 'asset', 'quantity transacted',
  'total (inclusive of fees and/or spread)',
];

// Binance trade history
const BINANCE_SIGNATURES = ['date(utc)', 'pair', 'side', 'executed'];

// Kraken ledger
const KRAKEN_SIGNATURES = ['txid', 'refid', 'time', 'type', 'asset', 'amount'];

// Bitpanda
const BITPANDA_SIGNATURES = ['transaction id', 'asset class', 'amount asset'];

// Bison (German headers)
const BISON_SIGNATURES_DE = ['datum', 'typ', 'kryptow\u00e4hrung', 'menge'];
const BISON_SIGNATURES_EN = ['date', 'type', 'cryptocurrency', 'amount'];

// Trade Republic (German headers)
const TRADE_REPUBLIC_SIGNATURES = ['datum', 'typ', 'isin', 'name', 'st\u00fcck'];
const TRADE_REPUBLIC_SIGNATURES_EN = ['date', 'type', 'isin', 'name', 'shares'];

function headersContainAll(
  headerSet: Set<string>,
  signatures: string[],
): boolean {
  return signatures.every((sig) => headerSet.has(sig));
}

/**
 * Auto-detect the exchange format from CSV text content.
 *
 * Parses the first row to extract headers, then matches against
 * known header signatures for each exchange.
 *
 * @param csvText - Raw CSV text
 * @returns Detected ExchangeFormat
 */
export function detectFormat(csvText: string): ExchangeFormat {
  // Try comma-delimited first
  let result = Papa.parse(csvText, {
    header: true,
    preview: 1,
    skipEmptyLines: true,
  });

  let headers = result.meta?.fields ?? [];

  // If we got 0 or 1 column, try semicolon
  if (headers.length <= 1) {
    result = Papa.parse(csvText, {
      header: true,
      preview: 1,
      delimiter: ';',
      skipEmptyLines: true,
    });
    headers = result.meta?.fields ?? [];
  }

  const headerSet: Set<string> = new Set(headers.map((h: string) => h.trim().toLowerCase()));

  if (headersContainAll(headerSet, COINBASE_SIGNATURES)) return 'coinbase';
  if (headersContainAll(headerSet, BINANCE_SIGNATURES)) return 'binance';
  if (headersContainAll(headerSet, KRAKEN_SIGNATURES)) return 'kraken';
  if (headersContainAll(headerSet, BITPANDA_SIGNATURES)) return 'bitpanda';
  if (headersContainAll(headerSet, BISON_SIGNATURES_DE) ||
      headersContainAll(headerSet, BISON_SIGNATURES_EN)) return 'bison';
  if (headersContainAll(headerSet, TRADE_REPUBLIC_SIGNATURES) ||
      headersContainAll(headerSet, TRADE_REPUBLIC_SIGNATURES_EN)) return 'trade_republic';

  return 'unknown';
}

/**
 * Parse a CEX CSV export into normalized Transaction objects.
 *
 * If format is not specified, auto-detects from headers.
 * For 'generic' format, a columnMapping must be provided.
 *
 * @param csvText       - Raw CSV text content
 * @param format        - Exchange format (auto-detected if omitted)
 * @param columnMapping - Required for 'generic' format
 * @returns Array of Transaction objects sorted by timestamp
 */
export function parseExchangeCsv(
  csvText: string,
  format?: ExchangeFormat,
  columnMapping?: ColumnMapping,
): Transaction[] {
  const fmt = format ?? detectFormat(csvText);

  // Determine delimiter
  const isSemicolon = ['bison', 'trade_republic'].includes(fmt);

  const parseResult = Papa.parse<Record<string, string>>(csvText, {
    header: true,
    skipEmptyLines: true,
    delimiter: isSemicolon ? ';' : undefined,
    transformHeader: (h: string) => h.trim(),
  });

  const rows = parseResult.data;
  if (!rows || rows.length === 0) return [];

  switch (fmt) {
    case 'coinbase':
      return parseCoinbaseCsv(rows);
    case 'binance':
      return parseBinanceCsv(rows);
    case 'kraken':
      return parseKrakenCsv(rows);
    case 'bitpanda':
      return parseBitpandaCsv(rows);
    case 'bison':
      return parseBisonCsv(rows);
    case 'trade_republic':
      return parseTradeRepublicCsv(rows);
    case 'generic':
      if (!columnMapping) {
        throw new Error('columnMapping is required for generic format');
      }
      return parseGenericCsv(rows, columnMapping);
    default:
      // Try generic with auto-detected columns
      throw new Error(
        `Unrecognized CSV format. Detected headers: ${parseResult.meta?.fields?.join(', ')}. ` +
        `Use 'generic' format with a columnMapping to import.`,
      );
  }
}

// Re-export individual parsers for direct use
export { parseCoinbaseCsv } from './coinbase';
export { parseBinanceCsv } from './binance';
export { parseKrakenCsv } from './kraken';
export { parseBitpandaCsv } from './bitpanda';
export { parseBisonCsv } from './bison';
export { parseTradeRepublicCsv } from './trade-republic';
export { parseGenericCsv, type ColumnMapping } from './generic';
export { parse1099DACsv } from './form-1099da';
