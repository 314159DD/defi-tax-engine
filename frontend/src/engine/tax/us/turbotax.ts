/**
 * TurboTax / H&R Block / TaxAct compatible CSV export.
 *
 * Ported from src/tax/us/turbotax_export.py.
 *
 * TurboTax expects (H&R Block extended format, accepted by all three):
 *   Date Sold, Currency Name, Purchase Date, Cost Basis, Proceeds,
 *   Gain or Loss, Holding Period, Amount Sold
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import type { Disposal, ReportFile } from '../../types';
import { buildCsv } from '../../reports/csv-export';

/** Convert ISO string to MM/DD/YYYY. */
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

function hpLabel(hp: string): string {
  if (['short-term', 'short', 'SHORT_TERM'].includes(hp)) return 'Short';
  return 'Long';
}

/**
 * Generate TurboTax-compatible CSV from Disposal objects.
 *
 * @param disposals - Array of Disposal objects
 * @param year      - Tax year to filter
 * @returns         ReportFile with CSV content
 */
export function generateTurboTaxExport(
  disposals: Disposal[],
  year: number,
): ReportFile {
  const headers = [
    'Date Sold', 'Currency Name', 'Purchase Date', 'Cost Basis',
    'Proceeds', 'Gain or Loss', 'Holding Period', 'Amount Sold',
  ];

  const rows: string[][] = [];

  for (const d of disposals) {
    const dy = parseInt(d.date.slice(0, 4), 10);
    if (dy !== year) continue;

    rows.push([
      fmtDateUS(d.date),
      d.token,
      'VARIOUS',
      d.costBasisUsd.toString(),
      d.proceedsUsd.toString(),
      d.gainLossUsd.toString(),
      hpLabel(d.holdingPeriod),
      d.amount.toString(),
    ]);
  }

  return {
    filename: `turbotax_${year}.csv`,
    content: buildCsv(headers, rows),
    mimeType: 'text/csv',
    reportType: 'turbotax',
  };
}
