/**
 * 1099-DA Reconciliation Report Generator.
 *
 * Ported from src/tax/us/reconciliation_report.py.
 *
 * Produces CSV and text summary reports from ReconciliationResult data.
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { ReportFile } from '../../types';
import {
  MatchConfidence,
  type ReconciliationResult,
} from './reconciliation';
import { buildCsv } from '../../reports/csv-export';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDecimal(value: Decimal | null): string {
  if (value === null) return '';
  return value.toFixed(2);
}

// ---------------------------------------------------------------------------
// CSV report
// ---------------------------------------------------------------------------

const CSV_COLUMNS = [
  'Status', 'Asset', 'Date', '1099-DA Proceeds', 'Our Proceeds',
  '1099-DA Cost Basis', 'Our Cost Basis', 'Discrepancy', 'Guidance',
];

/**
 * Generate a reconciliation report as CSV.
 */
export function generateReconciliationCsv(result: ReconciliationResult): ReportFile {
  const rows: string[][] = [];

  // Matched entries
  for (const entry of result.matched) {
    const form = entry.formEntry;
    const disp = entry.ourDisposal;
    const status = `Matched (${entry.confidence})`;

    let discrepancyText = '';
    let guidanceText = '';
    if (entry.discrepancies.length > 0) {
      discrepancyText = entry.discrepancies.map((d) => d.description).join('; ');
      guidanceText = entry.discrepancies.map((d) => d.guidance).join('; ');
    }

    rows.push([
      status,
      form.asset,
      form.dateSold,
      fmtDecimal(form.proceeds),
      fmtDecimal(disp.proceedsUsd),
      form.costBasis !== null ? fmtDecimal(form.costBasis) : '',
      fmtDecimal(disp.costBasisUsd),
      discrepancyText,
      guidanceText,
    ]);
  }

  // Unmatched 1099-DA entries
  for (const form of result.unmatched1099) {
    rows.push([
      'Missing Import',
      form.asset,
      form.dateSold,
      fmtDecimal(form.proceeds),
      '',
      form.costBasis !== null ? fmtDecimal(form.costBasis) : '',
      '',
      `On 1099-DA from ${form.brokerName} but not in imported data`,
      `Import your ${form.brokerName} transactions to resolve.`,
    ]);
  }

  // Unmatched our disposals (DeFi)
  for (const disp of result.unmatchedOurs) {
    rows.push([
      'DeFi / Not on 1099',
      disp.token,
      disp.date.slice(0, 10),
      '',
      fmtDecimal(disp.proceedsUsd),
      '',
      fmtDecimal(disp.costBasisUsd),
      'Not reported on any 1099-DA',
      'Self-report on Form 8949.',
    ]);
  }

  return {
    filename: 'reconciliation_report.csv',
    content: buildCsv(CSV_COLUMNS, rows),
    mimeType: 'text/csv',
    reportType: 'reconciliation',
  };
}

// ---------------------------------------------------------------------------
// Text summary report
// ---------------------------------------------------------------------------

/**
 * Generate a human-readable reconciliation summary.
 */
export function generateReconciliationSummary(result: ReconciliationResult): ReportFile {
  const lines: string[] = [];

  // Main summary
  lines.push(result.summaryText);
  lines.push('');

  // Detailed discrepancy listing
  if (result.discrepancies.length > 0) {
    lines.push('');
    lines.push('Detailed Discrepancies');
    lines.push('-'.repeat(40));

    for (let i = 0; i < result.discrepancies.length; i++) {
      const disc = result.discrepancies[i];
      lines.push('');
      lines.push(`  ${i + 1}. [${disc.type}] ${disc.description}`);
      if (disc.formValue !== null) {
        lines.push(`     1099-DA value: $${disc.formValue.toFixed(2)}`);
      }
      if (disc.ourValue !== null) {
        lines.push(`     Our value:     $${disc.ourValue.toFixed(2)}`);
      }
      lines.push(`     Guidance: ${disc.guidance}`);
    }
  }

  // Matched entries summary table
  if (result.matched.length > 0) {
    lines.push('');
    lines.push('');
    lines.push('Matched Transactions');
    lines.push('-'.repeat(40));

    for (const entry of result.matched) {
      const form = entry.formEntry;
      const disp = entry.ourDisposal;
      const tag = entry.confidence === MatchConfidence.EXACT ? 'EXACT' : 'FUZZY';
      lines.push(
        `  [${tag}] ${form.asset}  ${form.dateSold}  ` +
        `1099=$${form.proceeds.toFixed(2)}  ours=$${disp.proceedsUsd.toFixed(2)}`,
      );
    }
  }

  return {
    filename: 'reconciliation_summary.txt',
    content: lines.join('\n'),
    mimeType: 'text/plain',
    reportType: 'reconciliation_summary',
  };
}
