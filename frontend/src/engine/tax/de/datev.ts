/**
 * DATEV CSV export.
 *
 * Ported from src/tax/de/datev_export.py.
 *
 * Generates a CSV in standard DATEV Buchungssatz format for import into
 * DATEV accounting software (used by most German Steuerberater).
 *
 * Uses standard SKR03 accounts:
 *   - Konto 2740: Veraeusserungsgewinne aus privaten Geschaeften
 *   - Konto 2750: Veraeusserungsverluste aus privaten Geschaeften
 *   - Gegenkonto 1800: Bank
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Disposal, ReportFile } from '../../types';

/** Format date as DDMM (DATEV short format for Belegdatum). */
function fmtDateDatev(dt: string): string {
  try {
    const d = new Date(dt.slice(0, 10));
    if (isNaN(d.getTime())) return '';
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    return `${dd}${mm}`;
  } catch {
    return '';
  }
}

/** Format as DATEV currency: comma as decimal separator, no thousands, absolute value. */
function fmtEurDatev(amount: Decimal): string {
  return amount.abs().toFixed(2).replace('.', ',');
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
 * Generate DATEV Buchungssatz CSV from Disposal objects.
 *
 * @param disposals - Array of Disposal objects
 * @param year      - Tax year to filter
 * @returns         ReportFile with semicolon-delimited CSV content (ANSI encoding expected by DATEV)
 */
export function generateDatevExport(
  disposals: Disposal[],
  year: number,
): ReportFile {
  const lines: string[] = [];

  // DATEV header row
  lines.push(buildSemicolonRow([
    'Umsatz (ohne Soll/Haben-Kz)',
    'Soll/Haben-Kennzeichen',
    'Konto',
    'Gegenkonto (ohne BU-Schluessel)',
    'BU-Schluessel',
    'Belegdatum',
    'Belegfeld 1',
    'Buchungstext',
  ]));

  for (const d of disposals) {
    const dy = parseInt(d.date.slice(0, 4), 10);
    if (dy !== year) continue;

    const gain = d.gainLossUsd;
    const description =
      `Krypto ${d.token} ${d.amount.toFixed(6).replace(/0+$/, '').replace(/\.$/, '')}`;

    let konto: string;
    let gegenkonto: string;
    let sollHaben: string;

    if (gain.gte('0')) {
      // Gain: credit to Veraeusserungsgewinne
      konto = '2740';
      gegenkonto = '1800';
      sollHaben = 'H'; // Haben (credit)
    } else {
      // Loss: debit to Veraeusserungsverluste
      konto = '2750';
      gegenkonto = '1800';
      sollHaben = 'S'; // Soll (debit)
    }

    lines.push(buildSemicolonRow([
      fmtEurDatev(gain),
      sollHaben,
      konto,
      gegenkonto,
      '', // BU-Schluessel (empty)
      fmtDateDatev(d.date),
      d.txHash ? d.txHash.slice(0, 8) : '', // Belegfeld 1 (reference)
      description,
    ]));
  }

  return {
    filename: `datev_${year}.csv`,
    content: lines.join('\n') + '\n',
    mimeType: 'text/csv',
    reportType: 'datev',
  };
}
