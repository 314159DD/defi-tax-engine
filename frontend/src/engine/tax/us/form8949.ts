/**
 * IRS Form 8949 generator.
 *
 * Ported from src/tax/us/form_8949.py.
 *
 * Box codes (per IRS instructions):
 *   A = short-term, reported on 1099-B with basis
 *   B = short-term, reported on 1099-B without basis
 *   C = short-term, NOT reported on 1099-B (self-reported)
 *   D = long-term, reported on 1099-B with basis
 *   E = long-term, reported on 1099-B without basis
 *   F = long-term, NOT reported on 1099-B (self-reported)
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Disposal, ReportFile } from '../../types';
import { buildCsv } from '../../reports/csv-export';

// Brokers known to issue 1099-DA
const _1099_DA_BROKERS = new Set([
  'coinbase', 'kraken', 'gemini', 'binance.us', 'robinhood', 'paypal',
  'cash app', 'etoro',
]);

/** Convert ISO date string to MM/DD/YYYY. */
function fmtDateUS(dt: string): string {
  try {
    const d = new Date(dt.slice(0, 10));
    if (isNaN(d.getTime())) return dt;
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yyyy = d.getUTCFullYear();
    return `${mm}/${dd}/${yyyy}`;
  } catch {
    return dt;
  }
}

function isShortTerm(holdingPeriod: string): boolean {
  return ['short-term', 'short', 'SHORT_TERM'].includes(holdingPeriod);
}

/** Determine the Form 8949 checkbox code. */
function boxCode(holdingPeriod: string, isReported: boolean, hasBasis: boolean): string {
  const short = isShortTerm(holdingPeriod);
  if (short) {
    if (isReported && hasBasis) return 'A';
    if (isReported) return 'B';
    return 'C';
  }
  if (isReported && hasBasis) return 'D';
  if (isReported) return 'E';
  return 'F';
}

/**
 * Generate IRS Form 8949 CSV from Disposal objects.
 *
 * @param disposals  - Array of Disposal objects
 * @param year       - Tax year to filter
 * @param brokerMap  - Optional txHash -> broker name for 1099-DA flagging
 * @returns          ReportFile with CSV content
 */
export function generateForm8949(
  disposals: Disposal[],
  year: number,
  brokerMap: Record<string, string> = {},
): ReportFile {
  const headers = [
    'Part', 'Box', 'Description', 'Date Acquired', 'Date Sold',
    'Proceeds', 'Cost Basis', 'Adjustment Code', 'Adjustment Amount',
    'Gain or Loss', '1099-DA Reported',
  ];

  const rows: string[][] = [];

  for (const d of disposals) {
    const disposalYear = parseInt(d.date.slice(0, 4), 10);
    if (disposalYear !== year) continue;

    const broker = (brokerMap[d.txHash] ?? '').toLowerCase();
    const isReported = _1099_DA_BROKERS.has(broker);
    const hasBasis = isReported;

    const hp = d.holdingPeriod;
    const short = isShortTerm(hp);
    const part = short ? 'I (Short-Term)' : 'II (Long-Term)';
    const box = boxCode(hp, isReported, hasBasis);

    // Format amount: strip trailing zeros
    const description = `${d.amount.toFixed(8).replace(/0+$/, '').replace(/\.$/, '')} ${d.token}`;

    rows.push([
      part,
      box,
      description,
      'VARIOUS',
      fmtDateUS(d.date),
      d.proceedsUsd.toString(),
      d.costBasisUsd.toString(),
      '',
      '0',
      d.gainLossUsd.toString(),
      isReported ? 'Yes' : 'No',
    ]);
  }

  return {
    filename: `form_8949_${year}.csv`,
    content: buildCsv(headers, rows),
    mimeType: 'text/csv',
    reportType: 'form_8949',
  };
}
