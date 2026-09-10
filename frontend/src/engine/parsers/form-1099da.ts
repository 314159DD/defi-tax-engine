/**
 * 1099-DA CSV parser.
 *
 * Ported from src/importers/form_1099da.py.
 *
 * Parses 1099-DA form CSVs from major exchanges (Coinbase, Kraken, Binance.US)
 * and generic formats. Returns Form1099DAEntry objects for use in the
 * reconciliation engine.
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import * as Papa from 'papaparse';
import type { Form1099DAEntry } from '../tax/us/reconciliation';

// ---------------------------------------------------------------------------
// Parsing helpers
// ---------------------------------------------------------------------------

function parseDecimalOptional(value: string | undefined): Decimal | null {
  if (!value || !value.trim()) return null;
  const cleaned = value.trim().replace(/,/g, '').replace(/^\$/, '').trim();
  if (!cleaned || cleaned === '-' || ['n/a', 'na', 'none'].includes(cleaned.toLowerCase())) {
    return null;
  }
  try {
    return new Decimal(cleaned);
  } catch {
    return null;
  }
}

function parseDecimalRequired(value: string | undefined): Decimal {
  const result = parseDecimalOptional(value);
  return result ?? new Decimal('0');
}

function parseDateOptional(value: string | undefined): string | null {
  if (!value || !value.trim()) return null;
  const cleaned = value.trim().toUpperCase();
  if (['VARIOUS', 'N/A', 'NA', 'NONE', '-', ''].includes(cleaned)) return null;

  // Try YYYY-MM-DD
  let match = cleaned.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return `${match[1]}-${match[2]}-${match[3]}`;

  // Try MM/DD/YYYY
  match = cleaned.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (match) {
    return `${match[3]}-${match[1].padStart(2, '0')}-${match[2].padStart(2, '0')}`;
  }

  // Try MM/DD/YY
  match = cleaned.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2})$/);
  if (match) {
    const yr = parseInt(match[3], 10);
    const fullYear = yr < 50 ? 2000 + yr : 1900 + yr;
    return `${fullYear}-${match[1].padStart(2, '0')}-${match[2].padStart(2, '0')}`;
  }

  // Try DD/MM/YYYY
  match = cleaned.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (match) {
    return `${match[3]}-${match[2].padStart(2, '0')}-${match[1].padStart(2, '0')}`;
  }

  // Try ISO datetime
  try {
    const d = new Date(cleaned);
    if (!isNaN(d.getTime())) {
      return d.toISOString().slice(0, 10);
    }
  } catch {
    // fallthrough
  }

  return null;
}

function parseDateRequired(value: string | undefined): string {
  const result = parseDateOptional(value);
  if (!result) {
    throw new Error(`Could not parse required date: ${value}`);
  }
  return result;
}

function normalizeAsset(value: string): string {
  return value.trim().toUpperCase();
}

function detectCovered(row: Record<string, string>): boolean {
  for (const key of ['covered', 'is_covered', 'security_type', 'box_5']) {
    const val = (row[key] ?? '').trim().toLowerCase();
    if (['yes', 'true', '1', 'covered', 'y'].includes(val)) return true;
    if (['no', 'false', '0', 'uncovered', 'n', 'non-covered'].includes(val)) return false;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Header detection
// ---------------------------------------------------------------------------

const COINBASE_HEADERS = new Set(['asset name', 'date acquired', 'date sold or disposed', 'proceeds']);
const KRAKEN_HEADERS = new Set(['asset', 'date acquired', 'date of sale', 'gross proceeds']);
const BINANCE_HEADERS = new Set(['asset', 'date acquired', 'date sold', 'gross proceeds']);

function detect1099Format(headers: string[]): string {
  const lower = new Set(headers.map((h) => h.trim().toLowerCase()));

  if (Array.from(COINBASE_HEADERS).every((h) => lower.has(h))) return 'coinbase';
  if (Array.from(KRAKEN_HEADERS).every((h) => lower.has(h))) return 'kraken';
  if (Array.from(BINANCE_HEADERS).every((h) => lower.has(h))) return 'binance';
  return 'generic';
}

// ---------------------------------------------------------------------------
// Per-exchange parsers
// ---------------------------------------------------------------------------

function parseCoinbase1099Rows(rows: Record<string, string>[]): Form1099DAEntry[] {
  const entries: Form1099DAEntry[] = [];
  for (const row of rows) {
    const norm: Record<string, string> = {};
    for (const [k, v] of Object.entries(row)) {
      norm[k.trim().toLowerCase()] = v;
    }

    const asset = normalizeAsset(norm['asset name'] ?? norm['asset'] ?? '');
    if (!asset) continue;

    entries.push({
      asset,
      dateAcquired: parseDateOptional(norm['date acquired']),
      dateSold: parseDateRequired(norm['date sold or disposed'] ?? norm['date sold']),
      proceeds: parseDecimalRequired(norm['proceeds']),
      costBasis: parseDecimalOptional(norm['cost basis']),
      gainLoss: parseDecimalOptional(norm['gain or loss'] ?? norm['gain/loss']),
      brokerName: 'Coinbase',
      isCovered: detectCovered(norm),
      rawRow: row,
    });
  }
  return entries;
}

function parseKraken1099Rows(rows: Record<string, string>[]): Form1099DAEntry[] {
  const entries: Form1099DAEntry[] = [];
  for (const row of rows) {
    const norm: Record<string, string> = {};
    for (const [k, v] of Object.entries(row)) {
      norm[k.trim().toLowerCase()] = v;
    }

    const asset = normalizeAsset(norm['asset'] ?? '');
    if (!asset) continue;

    entries.push({
      asset,
      dateAcquired: parseDateOptional(norm['date acquired']),
      dateSold: parseDateRequired(norm['date of sale'] ?? norm['date sold']),
      proceeds: parseDecimalRequired(norm['gross proceeds'] ?? norm['proceeds']),
      costBasis: parseDecimalOptional(norm['cost basis']),
      gainLoss: parseDecimalOptional(norm['gain/loss'] ?? norm['gain or loss']),
      brokerName: 'Kraken',
      isCovered: detectCovered(norm),
      rawRow: row,
    });
  }
  return entries;
}

function parseBinance1099Rows(rows: Record<string, string>[]): Form1099DAEntry[] {
  const entries: Form1099DAEntry[] = [];
  for (const row of rows) {
    const norm: Record<string, string> = {};
    for (const [k, v] of Object.entries(row)) {
      norm[k.trim().toLowerCase()] = v;
    }

    const asset = normalizeAsset(norm['asset'] ?? '');
    if (!asset) continue;

    entries.push({
      asset,
      dateAcquired: parseDateOptional(norm['date acquired']),
      dateSold: parseDateRequired(norm['date sold']),
      proceeds: parseDecimalRequired(norm['gross proceeds'] ?? norm['proceeds']),
      costBasis: parseDecimalOptional(norm['cost basis']),
      gainLoss: parseDecimalOptional(norm['gain/loss'] ?? norm['gain or loss']),
      brokerName: 'Binance.US',
      isCovered: detectCovered(norm),
      rawRow: row,
    });
  }
  return entries;
}

function parseGeneric1099Rows(rows: Record<string, string>[]): Form1099DAEntry[] {
  const entries: Form1099DAEntry[] = [];

  if (rows.length === 0) return entries;

  // Auto-detect columns from first row keys
  const headers = Object.keys(rows[0]);
  const lowerMap = new Map<string, string>();
  for (const h of headers) {
    lowerMap.set(h.trim().toLowerCase(), h);
  }

  // Find required columns
  const assetCol =
    lowerMap.get('asset') ?? lowerMap.get('asset name') ?? lowerMap.get('token') ??
    lowerMap.get('currency') ?? lowerMap.get('symbol');
  const dateSoldCol =
    lowerMap.get('date sold') ?? lowerMap.get('date sold or disposed') ??
    lowerMap.get('date of sale') ?? lowerMap.get('sale date') ?? lowerMap.get('disposal date');
  const proceedsCol =
    lowerMap.get('proceeds') ?? lowerMap.get('gross proceeds') ??
    lowerMap.get('sale proceeds') ?? lowerMap.get('total proceeds');

  if (!assetCol || !dateSoldCol || !proceedsCol) {
    throw new Error(
      `Could not auto-detect required columns. Found: ${headers.join(', ')}`,
    );
  }

  // Optional columns
  const dateAcquiredCol =
    lowerMap.get('date acquired') ?? lowerMap.get('acquisition date') ??
    lowerMap.get('purchase date') ?? lowerMap.get('date purchased');
  const costBasisCol =
    lowerMap.get('cost basis') ?? lowerMap.get('cost') ?? lowerMap.get('basis');
  const gainLossCol =
    lowerMap.get('gain/loss') ?? lowerMap.get('gain or loss') ??
    lowerMap.get('gain_loss') ?? lowerMap.get('realized gain/loss');

  for (const row of rows) {
    const asset = normalizeAsset(row[assetCol] ?? '');
    if (!asset) continue;

    try {
      entries.push({
        asset,
        dateAcquired: dateAcquiredCol ? parseDateOptional(row[dateAcquiredCol]) : null,
        dateSold: parseDateRequired(row[dateSoldCol]),
        proceeds: parseDecimalRequired(row[proceedsCol]),
        costBasis: costBasisCol ? parseDecimalOptional(row[costBasisCol]) : null,
        gainLoss: gainLossCol ? parseDecimalOptional(row[gainLossCol]) : null,
        brokerName: 'Unknown Broker',
        isCovered: detectCovered(row),
        rawRow: row,
      });
    } catch {
      // Skip unparseable rows
    }
  }
  return entries;
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/**
 * Parse a 1099-DA CSV text into Form1099DAEntry objects.
 *
 * Auto-detects exchange format from CSV headers and parses accordingly.
 * Falls back to generic best-effort parsing if unrecognized.
 *
 * @param csvText - Raw CSV text content
 * @returns Array of Form1099DAEntry objects
 */
export function parse1099DACsv(csvText: string): Form1099DAEntry[] {
  const result = Papa.parse<Record<string, string>>(csvText, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h: string) => h.trim(),
  });

  if (!result.data || result.data.length === 0) return [];

  const headers = Object.keys(result.data[0]);
  const fmt = detect1099Format(headers);

  switch (fmt) {
    case 'coinbase':
      return parseCoinbase1099Rows(result.data);
    case 'kraken':
      return parseKraken1099Rows(result.data);
    case 'binance':
      return parseBinance1099Rows(result.data);
    default:
      return parseGeneric1099Rows(result.data);
  }
}
