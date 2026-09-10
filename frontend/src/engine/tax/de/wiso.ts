/**
 * WISO Steuer CSV export.
 *
 * Ported from src/tax/de/wiso_export.py.
 *
 * Generates a CSV compatible with WISO Steuer (Buhl Data),
 * matching the format used by CoinTracking's WISO export.
 *
 * Columns (semicolon-delimited):
 *   Typ, Kaufdatum, Kaufkurs, Kaufmenge, Kaufgebuehren,
 *   Verkaufsdatum, Verkaufskurs, Verkaufmenge, Verkaufsgebuehren,
 *   Gewinn/Verlust
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Disposal, ReportFile } from '../../types';
import { HoldingPeriod } from '../../types';

/** Format date as DD.MM.YYYY. */
function fmtDateDE(dt: string): string {
  try {
    const d = new Date(dt.slice(0, 10));
    if (isNaN(d.getTime())) return dt;
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const yyyy = d.getUTCFullYear();
    return `${dd}.${mm}.${yyyy}`;
  } catch {
    return dt;
  }
}

/** Format as German decimal: 1234,56 */
function fmtEur(amount: Decimal): string {
  return amount.toFixed(2).replace('.', ',');
}

/** Escape a semicolon-delimited field. */
function escField(val: string): string {
  if (val.includes(';') || val.includes('"') || val.includes('\n')) {
    return '"' + val.replace(/"/g, '""') + '"';
  }
  return val;
}

function buildSemicolonRow(fields: string[]): string {
  return fields.map(escField).join(';');
}

/**
 * Generate WISO Steuer-compatible CSV from Disposal objects.
 *
 * @param disposals - Array of Disposal objects
 * @param year      - Tax year to filter
 * @returns         ReportFile with semicolon-delimited CSV content
 */
export function generateWisoExport(
  disposals: Disposal[],
  year: number,
): ReportFile {
  const lines: string[] = [];

  lines.push(buildSemicolonRow([
    'Typ',
    'Kaufdatum',
    'Kaufkurs',
    'Kaufmenge',
    'Kaufgebuehren',
    'Verkaufsdatum',
    'Verkaufskurs',
    'Verkaufmenge',
    'Verkaufsgebuehren',
    'Gewinn/Verlust',
  ]));

  for (const d of disposals) {
    const dy = parseInt(d.date.slice(0, 4), 10);
    if (dy !== year) continue;

    // Determine type label
    const isExempt =
      d.holdingPeriod === 'exempt' ||
      d.holdingPeriodEnum === HoldingPeriod.EXEMPT;
    const typ = isExempt ? 'Steuerfrei' : 'Veraeusserung';

    // Compute per-unit prices
    let kaufkurs: Decimal;
    let verkaufskurs: Decimal;
    if (d.amount.gt('0')) {
      kaufkurs = d.costBasisUsd.div(d.amount);
      verkaufskurs = d.proceedsUsd.div(d.amount);
    } else {
      kaufkurs = new Decimal('0');
      verkaufskurs = new Decimal('0');
    }

    // Acquisition date: use earliest lot date if available, else "Verschiedene"
    let acqDate = 'Verschiedene';
    if (d.lotsConsumed && d.lotsConsumed.length > 0) {
      acqDate = fmtDateDE(d.lotsConsumed[0].acquisitionDate);
    }

    lines.push(buildSemicolonRow([
      typ,
      acqDate,
      fmtEur(kaufkurs),
      d.amount.toString(),
      '0,00', // Buy fees (already included in cost basis)
      fmtDateDE(d.date),
      fmtEur(verkaufskurs),
      d.amount.toString(),
      '0,00', // Sell fees (already deducted from proceeds)
      fmtEur(d.gainLossUsd),
    ]));
  }

  return {
    filename: `wiso_${year}.csv`,
    content: lines.join('\n') + '\n',
    mimeType: 'text/csv',
    reportType: 'wiso',
  };
}
