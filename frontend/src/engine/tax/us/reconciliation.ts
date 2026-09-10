/**
 * 1099-DA Reconciliation Engine.
 *
 * Ported from src/tax/us/reconciliation.py.
 *
 * Matches 1099-DA form entries against calculated disposals to identify
 * discrepancies and generate actionable guidance for US tax filers.
 *
 * Matching logic:
 *   1. Same asset (case-insensitive)
 *   2. Same date (+/-1 day tolerance)
 *   3. Proceeds within 2% tolerance for EXACT, 5% for FUZZY
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';
import type { Disposal } from '../../types';

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export enum MatchConfidence {
  EXACT = 'exact',
  FUZZY = 'fuzzy',
  UNMATCHED = 'unmatched',
}

export enum DiscrepancyType {
  MISSING_IMPORT = 'missing_import',
  DEFI_NOT_ON_1099 = 'defi_not_on_1099',
  COST_BASIS_DIFF = 'cost_basis_diff',
  PROCEEDS_DIFF = 'proceeds_diff',
}

// ---------------------------------------------------------------------------
// Data models
// ---------------------------------------------------------------------------

/** A single line item from a 1099-DA form. */
export interface Form1099DAEntry {
  asset: string;
  dateAcquired: string | null; // ISO date or null for 'VARIOUS'
  dateSold: string;            // ISO date
  proceeds: Decimal;
  costBasis: Decimal | null;
  gainLoss: Decimal | null;
  brokerName: string;
  isCovered: boolean;
  rawRow: Record<string, string>;
}

/** A single discrepancy between 1099-DA and our calculated data. */
export interface Discrepancy {
  type: DiscrepancyType;
  description: string;
  formValue: Decimal | null;
  ourValue: Decimal | null;
  guidance: string;
}

/** A matched pair: 1099-DA entry <-> our disposal. */
export interface MatchedEntry {
  formEntry: Form1099DAEntry;
  ourDisposal: Disposal;
  confidence: MatchConfidence;
  discrepancies: Discrepancy[];
}

/** Complete reconciliation output. */
export interface ReconciliationResult {
  matched: MatchedEntry[];
  unmatched1099: Form1099DAEntry[];
  unmatchedOurs: Disposal[];
  discrepancies: Discrepancy[];
  total1099Proceeds: Decimal;
  totalOurProceeds: Decimal;
  matchRate: Decimal;
  summaryText: string;
}

// ---------------------------------------------------------------------------
// Matching helpers
// ---------------------------------------------------------------------------

function normalizeAsset(asset: string): string {
  return asset.trim().toUpperCase();
}

function parseDateOnly(iso: string): Date {
  return new Date(iso.slice(0, 10) + 'T00:00:00Z');
}

function datesMatchExact(d1: Date, d2: Date): boolean {
  return d1.getTime() === d2.getTime();
}

function datesMatchFuzzy(d1: Date, d2: Date, toleranceDays: number = 1): boolean {
  const diffMs = Math.abs(d1.getTime() - d2.getTime());
  return diffMs <= toleranceDays * 86400000;
}

function proceedsMatchExact(
  p1: Decimal, p2: Decimal, tolerancePct: Decimal = new Decimal('0.02'),
): boolean {
  if (p1.isZero() && p2.isZero()) return true;
  if (p1.isZero() || p2.isZero()) return false;
  const diffPct = p1.minus(p2).abs().div(Decimal.max(p1.abs(), p2.abs()));
  return diffPct.lte(tolerancePct);
}

function proceedsMatchFuzzy(
  p1: Decimal, p2: Decimal, tolerancePct: Decimal = new Decimal('0.05'),
): boolean {
  return proceedsMatchExact(p1, p2, tolerancePct);
}

// ---------------------------------------------------------------------------
// Guidance text generators
// ---------------------------------------------------------------------------

function guidanceMissingImport(broker: string): string {
  return (
    `This transaction appears on your 1099-DA from ${broker} but not in ` +
    `your imported data. Import your ${broker} transactions to resolve.`
  );
}

function guidanceDefiNotOn1099(): string {
  return (
    'This DeFi transaction is not reported on any 1099-DA. ' +
    'You must self-report it on Form 8949.'
  );
}

function guidanceCostBasisDiff(formValue: Decimal, ourValue: Decimal): string {
  return (
    `Your 1099-DA shows cost basis of $${formValue.toFixed(2)} but we calculated ` +
    `$${ourValue.toFixed(2)}. This may be due to transfers between wallets ` +
    `affecting lot ordering.`
  );
}

function guidanceProceedsDiff(diff: Decimal): string {
  return (
    `Proceeds differ by $${diff.abs().toFixed(2)}. This is typically due to ` +
    `rounding or fee treatment differences.`
  );
}

// ---------------------------------------------------------------------------
// Core reconciliation engine
// ---------------------------------------------------------------------------

/**
 * Reconcile 1099-DA form entries against our calculated disposals.
 *
 * Matching priority:
 *   1. EXACT: same asset + same date + proceeds within 2%
 *   2. FUZZY: same asset + date +/-1 day + proceeds within 5%
 *   3. UNMATCHED: no match found
 *
 * @param formEntries   - Array of Form1099DAEntry objects
 * @param ourDisposals  - Array of Disposal objects
 * @returns ReconciliationResult
 */
export function reconcile(
  formEntries: Form1099DAEntry[],
  ourDisposals: Disposal[],
): ReconciliationResult {
  const matched: MatchedEntry[] = [];
  const allDiscrepancies: Discrepancy[] = [];

  // Track available disposals
  const availableDisposals = [...ourDisposals];
  const unmatched1099: Form1099DAEntry[] = [];

  for (const formEntry of formEntries) {
    let bestMatch: Disposal | null = null;
    let bestConfidence = MatchConfidence.UNMATCHED;
    let bestIndex = -1;

    const formAsset = normalizeAsset(formEntry.asset);
    const formDate = parseDateOnly(formEntry.dateSold);
    const formProceeds = formEntry.proceeds;

    for (let idx = 0; idx < availableDisposals.length; idx++) {
      const disposal = availableDisposals[idx];
      const dispAsset = normalizeAsset(disposal.token);
      const dispDate = parseDateOnly(disposal.date);
      const dispProceeds = disposal.proceedsUsd;

      // Must be same asset
      if (formAsset !== dispAsset) continue;

      // Check EXACT match first
      if (datesMatchExact(formDate, dispDate) &&
          proceedsMatchExact(formProceeds, dispProceeds)) {
        bestMatch = disposal;
        bestConfidence = MatchConfidence.EXACT;
        bestIndex = idx;
        break; // exact is best possible
      }

      // Check FUZZY match (only upgrade if we haven't found an exact or fuzzy yet)
      if (datesMatchFuzzy(formDate, dispDate) &&
          proceedsMatchFuzzy(formProceeds, dispProceeds)) {
        if (bestConfidence === MatchConfidence.UNMATCHED) {
          bestMatch = disposal;
          bestConfidence = MatchConfidence.FUZZY;
          bestIndex = idx;
        }
      }
    }

    if (bestMatch !== null && bestIndex >= 0) {
      availableDisposals.splice(bestIndex, 1);

      const entryDiscrepancies: Discrepancy[] = [];

      // Check cost basis difference
      if (formEntry.costBasis !== null) {
        if (!proceedsMatchExact(formEntry.costBasis, bestMatch.costBasisUsd)) {
          const disc: Discrepancy = {
            type: DiscrepancyType.COST_BASIS_DIFF,
            description:
              `Cost basis mismatch for ${formAsset}: ` +
              `1099-DA=$${formEntry.costBasis.toFixed(2)}, ` +
              `ours=$${bestMatch.costBasisUsd.toFixed(2)}`,
            formValue: formEntry.costBasis,
            ourValue: bestMatch.costBasisUsd,
            guidance: guidanceCostBasisDiff(formEntry.costBasis, bestMatch.costBasisUsd),
          };
          entryDiscrepancies.push(disc);
          allDiscrepancies.push(disc);
        }
      }

      // Check proceeds difference
      const proceedsDiff = formEntry.proceeds.minus(bestMatch.proceedsUsd);
      if (proceedsDiff.abs().gt('0.01')) {
        const disc: Discrepancy = {
          type: DiscrepancyType.PROCEEDS_DIFF,
          description:
            `Proceeds differ for ${formAsset}: ` +
            `1099-DA=$${formEntry.proceeds.toFixed(2)}, ` +
            `ours=$${bestMatch.proceedsUsd.toFixed(2)}`,
          formValue: formEntry.proceeds,
          ourValue: bestMatch.proceedsUsd,
          guidance: guidanceProceedsDiff(proceedsDiff),
        };
        entryDiscrepancies.push(disc);
        allDiscrepancies.push(disc);
      }

      matched.push({
        formEntry,
        ourDisposal: bestMatch,
        confidence: bestConfidence,
        discrepancies: entryDiscrepancies,
      });
    } else {
      unmatched1099.push(formEntry);
      const disc: Discrepancy = {
        type: DiscrepancyType.MISSING_IMPORT,
        description:
          `${formAsset} sold on ${formEntry.dateSold} for ` +
          `$${formEntry.proceeds.toFixed(2)} appears on 1099-DA from ` +
          `${formEntry.brokerName} but not in your imported data.`,
        formValue: formEntry.proceeds,
        ourValue: null,
        guidance: guidanceMissingImport(formEntry.brokerName),
      };
      allDiscrepancies.push(disc);
    }
  }

  // Remaining disposals = DeFi/self-custody not on any 1099
  const unmatchedOurs = availableDisposals;
  for (const disposal of unmatchedOurs) {
    const disc: Discrepancy = {
      type: DiscrepancyType.DEFI_NOT_ON_1099,
      description:
        `${normalizeAsset(disposal.token)} disposed on ` +
        `${disposal.date.slice(0, 10)} for $${disposal.proceedsUsd.toFixed(2)} ` +
        `is not reported on any 1099-DA.`,
      formValue: null,
      ourValue: disposal.proceedsUsd,
      guidance: guidanceDefiNotOn1099(),
    };
    allDiscrepancies.push(disc);
  }

  // Compute summary statistics
  let total1099 = new Decimal('0');
  for (const e of formEntries) total1099 = total1099.plus(e.proceeds);

  let totalOurs = new Decimal('0');
  for (const d of ourDisposals) totalOurs = totalOurs.plus(d.proceedsUsd);

  const totalEntries = formEntries.length;
  const matchRate = totalEntries > 0
    ? new Decimal(matched.length).div(totalEntries).times(100).toDecimalPlaces(2)
    : new Decimal('100');

  // Build summary text
  const summaryLines: string[] = [
    'Reconciliation Summary',
    '='.repeat(40),
    `Total 1099-DA entries:     ${formEntries.length}`,
    `Total calculated disposals: ${ourDisposals.length}`,
    '',
    `Matched (exact):           ${matched.filter((m) => m.confidence === MatchConfidence.EXACT).length}`,
    `Matched (fuzzy):           ${matched.filter((m) => m.confidence === MatchConfidence.FUZZY).length}`,
    `Unmatched on 1099-DA:      ${unmatched1099.length}`,
    `Unmatched in our data:     ${unmatchedOurs.length}`,
    '',
    `Match rate:                ${matchRate.toString()}%`,
    '',
    `Total 1099-DA proceeds:    $${total1099.toFixed(2)}`,
    `Total our proceeds:        $${totalOurs.toFixed(2)}`,
    `Difference:                $${total1099.minus(totalOurs).abs().toFixed(2)}`,
    '',
    `Discrepancies found:       ${allDiscrepancies.length}`,
  ];

  if (unmatched1099.length > 0) {
    summaryLines.push('');
    summaryLines.push('ACTION NEEDED: Import missing transactions');
    const brokers = Array.from(new Set(unmatched1099.map((e) => e.brokerName)));
    for (const broker of brokers.sort()) {
      const count = unmatched1099.filter((e) => e.brokerName === broker).length;
      summaryLines.push(`  - ${broker}: ${count} unmatched transaction(s)`);
    }
  }

  if (unmatchedOurs.length > 0) {
    summaryLines.push('');
    summaryLines.push('ACTION NEEDED: Self-report DeFi disposals on Form 8949');
    summaryLines.push(`  - ${unmatchedOurs.length} disposal(s) not on any 1099-DA`);
  }

  return {
    matched,
    unmatched1099: unmatched1099,
    unmatchedOurs: unmatchedOurs,
    discrepancies: allDiscrepancies,
    total1099Proceeds: total1099,
    totalOurProceeds: totalOurs,
    matchRate,
    summaryText: summaryLines.join('\n'),
  };
}
