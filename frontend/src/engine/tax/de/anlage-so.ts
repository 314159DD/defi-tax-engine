/**
 * Anlage SO (Sonstige Einkuenfte) CSV generator.
 *
 * Ported from src/tax/de/anlage_so.py.
 *
 * Generates a CSV file formatted for use with German tax filing software
 * and Steuerberater (tax advisors).
 *
 * Structure:
 *   Section 1: Private Veraeusserungsgeschaefte (§23 EStG) - crypto disposals
 *   Section 2: Sonstige Einkuenfte (§22 Nr. 3 EStG) - staking rewards, etc.
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Disposal, ReportFile } from '../../types';
import { HoldingPeriod } from '../../types';
import type { IncomeEvent } from '../us/income-report';

/** Format date as DD.MM.YYYY (German convention). */
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

/** Format Decimal as German currency string: 1234,56 */
function fmtEur(amount: Decimal): string {
  return amount.toFixed(2).replace('.', ',');
}

function isShortTerm(d: Disposal): boolean {
  const hp = d.holdingPeriod;
  return ['short-term', 'short', 'SHORT_TERM'].includes(hp);
}

function isExempt(d: Disposal): boolean {
  return d.holdingPeriod === 'exempt' ||
    d.holdingPeriodEnum === HoldingPeriod.EXEMPT;
}

const TYPE_LABELS_DE: Record<string, string> = {
  reward: 'Staking Reward',
  airdrop: 'Airdrop',
  mining: 'Mining',
  validator: 'Validator',
  interest: 'DeFi-Zinsen',
};

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
 * Generate Anlage SO CSV.
 *
 * @param disposals    - Array of Disposal objects
 * @param incomeEvents - Array of income event objects
 * @param year         - Tax year
 * @returns            ReportFile with semicolon-delimited CSV content
 */
export function generateAnlageSO(
  disposals: Disposal[],
  incomeEvents: IncomeEvent[],
  year: number,
): ReportFile {
  const lines: string[] = [];

  // --- Section 1: Private Veraeusserungsgeschaefte (§23 EStG) ---
  lines.push(escField('Anlage SO - Private Veraeusserungsgeschaefte (Kryptowaehrungen)'));
  lines.push(escField(`Steuerjahr: ${year}`));
  lines.push('');

  lines.push(buildSemicolonRow([
    'Zeile',
    'Art des Wirtschaftsguts',
    'Anschaffungsdatum',
    'Veraeusserungsdatum',
    'Veraeusserungspreis (EUR)',
    'Anschaffungskosten (EUR)',
    'Gewinn/Verlust (EUR)',
    'Haltefrist',
    'Steuerpflichtig',
  ]));

  let zeile = 1;
  let totalTaxableGain = new Decimal('0');
  let totalExemptGain = new Decimal('0');

  for (const d of disposals) {
    const dy = parseInt(d.date.slice(0, 4), 10);
    if (dy !== year) continue;

    const short = isShortTerm(d);
    const exempt = isExempt(d);
    const haltefrist = short ? '<=365 Tage' : '>365 Tage (steuerfrei)';
    const steuerpflichtig = short ? 'Ja' : 'Nein';

    if (short) {
      totalTaxableGain = totalTaxableGain.plus(d.gainLossUsd);
    } else {
      totalExemptGain = totalExemptGain.plus(d.gainLossUsd);
    }

    const description =
      `${d.amount.toFixed(8).replace(/0+$/, '').replace(/\.$/, '')} ${d.token}`;

    lines.push(buildSemicolonRow([
      String(zeile),
      description,
      'Verschiedene',
      fmtDateDE(d.date),
      fmtEur(d.proceedsUsd),
      fmtEur(d.costBasisUsd),
      fmtEur(d.gainLossUsd),
      haltefrist,
      steuerpflichtig,
    ]));
    zeile++;
  }

  lines.push('');
  lines.push(buildSemicolonRow([
    '', 'Summe steuerpflichtig', '', '', '', '', fmtEur(totalTaxableGain),
  ]));
  lines.push(buildSemicolonRow([
    '', 'Summe steuerfrei (Spekulationsfrist)', '', '', '', '', fmtEur(totalExemptGain),
  ]));

  // --- Section 2: Sonstige Einkuenfte (§22 Nr. 3 EStG) ---
  lines.push('');
  lines.push('');
  lines.push(escField('Sonstige Einkuenfte aus Kryptowaehrungen (\u00a722 Nr. 3 EStG)'));
  lines.push('');
  lines.push(buildSemicolonRow([
    'Zeile', 'Art der Einkuenfte', 'Datum', 'Token', 'Menge', 'Wert (EUR)',
  ]));

  let totalIncome = new Decimal('0');
  let incomeZeile = 1;

  for (const e of incomeEvents) {
    const dateYear = e.date.slice(0, 4);
    if (dateYear !== String(year)) continue;

    const usdVal = new Decimal(e.usdValue || '0');
    totalIncome = totalIncome.plus(usdVal);

    lines.push(buildSemicolonRow([
      String(incomeZeile),
      TYPE_LABELS_DE[e.txType] ?? e.txType,
      fmtDateDE(e.date),
      e.token,
      e.amount,
      fmtEur(usdVal),
    ]));
    incomeZeile++;
  }

  lines.push('');
  lines.push(buildSemicolonRow([
    '', 'Summe Sonstige Einkuenfte', '', '', '', fmtEur(totalIncome),
  ]));

  return {
    filename: `anlage_so_${year}.csv`,
    content: lines.join('\n') + '\n',
    mimeType: 'text/csv',
    reportType: 'anlage_so',
  };
}
