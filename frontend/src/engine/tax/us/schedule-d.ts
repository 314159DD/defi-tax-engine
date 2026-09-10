/**
 * IRS Schedule D summary generator.
 *
 * Ported from src/tax/us/schedule_d.py.
 *
 * Schedule D aggregates the totals from Form 8949:
 *   - Part I:  Short-term capital gains/losses
 *   - Part II: Long-term capital gains/losses
 *   - Part III: Net capital gain/loss + carryover calculation
 *
 * Capital loss carryover rules:
 *   - Net capital loss limited to $3,000/year deduction against ordinary income
 *   - Excess carries over indefinitely to future years
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Disposal, ReportFile } from '../../types';

const MAX_DEDUCTIBLE_LOSS = new Decimal('-3000'); // IRS annual cap

function isShortTerm(d: Disposal): boolean {
  const hp = d.holdingPeriod;
  return ['short-term', 'short', 'SHORT_TERM'].includes(hp);
}

function fmtUsd(d: Decimal): string {
  const num = d.toNumber();
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * Generate Schedule D summary as a text report.
 *
 * @param disposals          - Array of Disposal objects
 * @param year               - Tax year
 * @param method             - Cost basis method label
 * @param priorYearCarryover - Unused loss from prior years (positive number)
 * @returns                  ReportFile with text content
 */
export function generateScheduleD(
  disposals: Disposal[],
  year: number,
  method: string = 'FIFO',
  priorYearCarryover: Decimal = new Decimal('0'),
): ReportFile {
  // Filter to the correct year
  const yearDisposals = disposals.filter((d) => {
    const dy = parseInt(d.date.slice(0, 4), 10);
    return dy === year;
  });

  let stProceeds = new Decimal('0');
  let stBasis = new Decimal('0');
  let stNet = new Decimal('0');
  let ltProceeds = new Decimal('0');
  let ltBasis = new Decimal('0');
  let ltNet = new Decimal('0');

  for (const d of yearDisposals) {
    if (isShortTerm(d)) {
      stProceeds = stProceeds.plus(d.proceedsUsd);
      stBasis = stBasis.plus(d.costBasisUsd);
      stNet = stNet.plus(d.gainLossUsd);
    } else {
      ltProceeds = ltProceeds.plus(d.proceedsUsd);
      ltBasis = ltBasis.plus(d.costBasisUsd);
      ltNet = ltNet.plus(d.gainLossUsd);
    }
  }

  // Apply prior year carryover
  if (priorYearCarryover.gt('0')) {
    stNet = stNet.minus(priorYearCarryover);
  }

  const net = stNet.plus(ltNet);

  let deductible = new Decimal('0');
  let carryover = new Decimal('0');
  if (net.lt('0')) {
    deductible = Decimal.max(net, MAX_DEDUCTIBLE_LOSS);
    carryover = net.minus(deductible).abs();
  }

  const lines: string[] = [
    `Schedule D \u2014 Capital Gains and Losses (${year}, ${method})`,
    '='.repeat(60),
    '',
    'PART I \u2014 Short-Term Capital Gains and Losses',
    `  Proceeds:    $${fmtUsd(stProceeds).padStart(14)}`,
    `  Cost Basis:  $${fmtUsd(stBasis).padStart(14)}`,
    `  Net:         $${fmtUsd(stNet).padStart(14)}`,
    '',
    'PART II \u2014 Long-Term Capital Gains and Losses',
    `  Proceeds:    $${fmtUsd(ltProceeds).padStart(14)}`,
    `  Cost Basis:  $${fmtUsd(ltBasis).padStart(14)}`,
    `  Net:         $${fmtUsd(ltNet).padStart(14)}`,
    '',
    'PART III \u2014 Summary',
    `  Net Capital Gain/(Loss):  $${fmtUsd(net).padStart(12)}`,
  ];

  if (net.lt('0')) {
    lines.push(`  Deductible Loss (max $3k): $${fmtUsd(deductible).padStart(12)}`);
    lines.push(`  Carryover to Next Year:   $${fmtUsd(carryover).padStart(12)}`);
  }

  return {
    filename: `schedule_d_${year}.txt`,
    content: lines.join('\n'),
    mimeType: 'text/plain',
    reportType: 'schedule_d',
  };
}
