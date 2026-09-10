/**
 * US ordinary income report for crypto.
 *
 * Ported from src/tax/us/income_report.py.
 *
 * Taxable income event types (IRS treatment):
 *   - staking rewards  -> ordinary income at FMV on date of receipt
 *   - airdrop          -> ordinary income at FMV on date of receipt
 *   - mining/validator -> ordinary income at FMV on date of receipt
 *   - interest         -> ordinary income
 *
 * Reported on Schedule 1 (Additional Income), NOT Schedule D.
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import type { ReportFile } from '../../types';
import { buildCsv } from '../../reports/csv-export';

/** An income event to be reported. */
export interface IncomeEvent {
  date: string;       // ISO date/datetime
  txType: string;     // reward, airdrop, mining, validator, interest
  token: string;
  amount: string;     // Decimal-as-string
  usdValue: string;   // FMV at receipt as string
  txHash: string;
  chain: string;
}

const CATEGORY_LABEL: Record<string, string> = {
  reward: 'Staking Reward',
  airdrop: 'Airdrop',
  mining: 'Mining Income',
  validator: 'Validator Income',
  interest: 'DeFi Interest',
};

/**
 * Generate income CSV from income event objects.
 *
 * @param incomeEvents - Array of income event objects
 * @param year         - Tax year to filter
 * @returns            ReportFile with CSV content
 */
export function generateIncomeReport(
  incomeEvents: IncomeEvent[],
  year: number,
): ReportFile {
  const headers = [
    'Date', 'Type', 'Category', 'Chain', 'Token', 'Amount',
    'USD Value (FMV at Receipt)', 'TX Hash',
  ];

  const rows: string[][] = [];

  for (const e of incomeEvents) {
    const dateYear = e.date.slice(0, 4);
    if (dateYear !== String(year)) continue;

    const category = CATEGORY_LABEL[e.txType] ??
      (e.txType.charAt(0).toUpperCase() + e.txType.slice(1));

    rows.push([
      e.date.slice(0, 10),
      e.txType,
      category,
      e.chain,
      e.token,
      e.amount,
      e.usdValue,
      e.txHash,
    ]);
  }

  return {
    filename: `income_report_${year}.csv`,
    content: buildCsv(headers, rows),
    mimeType: 'text/csv',
    reportType: 'income_report',
  };
}
