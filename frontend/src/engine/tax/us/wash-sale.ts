/**
 * Wash sale detection and basis adjustment for US tax rules.
 *
 * IRS wash sale rule: If you sell a security at a loss and buy a substantially
 * identical security within 30 days before or after the sale, the loss is
 * disallowed. The disallowed loss is added to the cost basis of the replacement
 * lot.
 *
 * IMPORTANT: As of 2026, the IRS has not definitively ruled that crypto wash
 * sales apply. However, Section 1091 may be extended to digital assets in future
 * guidance. This module provides tracking and warnings for conservative filers.
 *
 * All monetary values use Decimal -- NEVER native number for money.
 *
 * Ported from: src/tax/us/wash_sale.py
 */

import Decimal from 'decimal.js';
import type { TaxLot } from '../../types';

// Wash sale window: 30 days before + 30 days after = 61-day total window
const WASH_SALE_WINDOW = 30;

/** Milliseconds per day for date arithmetic. */
const MS_PER_DAY = 86_400_000;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Represents a wash sale window triggered by a disposal at a loss.
 *
 * The window spans from (saleDate - 30 days) to (saleDate + 30 days).
 * Any acquisition of the same token within this window creates a wash sale:
 * the loss is disallowed and added to the replacement lot's basis.
 */
export interface WashSaleWindow {
  token: string;
  saleDate: string; // ISO date
  windowStart: string; // ISO date
  windowEnd: string; // ISO date
  disallowedLoss: Decimal; // the loss that is disallowed (positive value)
  replacementLotId: string | null; // lot that triggered the wash sale
  disposalTxHash: string | null; // the sale transaction
}

export interface WashSaleWarning {
  warning: true;
  token: string;
  acquisitionDate: string;
  saleDate: string;
  windowStart: string;
  windowEnd: string;
  lotId: string | null;
}

/** Dict-like input for a disposal to check for wash sales. */
export interface WashSaleDisposalInput {
  token: string;
  disposalDate: string | Date; // ISO date or Date object
  gainLossUsd: string | number | Decimal;
  txHash?: string;
}

/** Dict-like input for an acquisition to check for wash sales. */
export interface WashSaleAcquisitionInput {
  token: string;
  acquisitionDate: string | Date; // ISO date or Date object
  lotId?: string;
  id?: string;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function toDecimal(value: unknown): Decimal {
  if (value instanceof Decimal) return value;
  try {
    return new Decimal(String(value));
  } catch {
    return new Decimal('0');
  }
}

function toDateStr(value: string | Date): string {
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }
  return String(value).slice(0, 10);
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function dateInRange(dateStr: string, start: string, end: string): boolean {
  return dateStr >= start && dateStr <= end;
}

// ---------------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------------

export function washSaleWindowToDict(w: WashSaleWindow): Record<string, unknown> {
  return {
    token: w.token,
    saleDate: w.saleDate,
    windowStart: w.windowStart,
    windowEnd: w.windowEnd,
    disallowedLoss: w.disallowedLoss.toString(),
    replacementLotId: w.replacementLotId,
    disposalTxHash: w.disposalTxHash,
  };
}

/** Check if a wash sale window is currently active. */
export function isWindowActive(w: WashSaleWindow, asOf: string): boolean {
  return dateInRange(asOf, w.windowStart, w.windowEnd);
}

// ---------------------------------------------------------------------------
// Core functions
// ---------------------------------------------------------------------------

/**
 * Detect wash sale violations by cross-referencing disposals with acquisitions.
 *
 * @param disposals - list of disposal dicts with token, disposalDate, gainLossUsd, txHash
 * @param acquisitions - list of acquisition dicts with token, acquisitionDate, lotId
 * @returns List of WashSaleWindow objects for each detected wash sale.
 */
export function checkWashSales(
  disposals: WashSaleDisposalInput[],
  acquisitions: WashSaleAcquisitionInput[],
): WashSaleWindow[] {
  const windows: WashSaleWindow[] = [];

  for (const disposal of disposals) {
    // Only consider disposals at a loss
    const gl = toDecimal(disposal.gainLossUsd);
    if (gl.gte(new Decimal('0'))) {
      continue;
    }

    const token = disposal.token.toUpperCase();
    const saleDate = toDateStr(disposal.disposalDate);
    const lossAmount = gl.abs();
    const windowStart = addDays(saleDate, -WASH_SALE_WINDOW);
    const windowEnd = addDays(saleDate, WASH_SALE_WINDOW);

    // Find any acquisition of the same token within the window
    let replacementLotId: string | null = null;
    for (const acq of acquisitions) {
      if (acq.token.toUpperCase() !== token) {
        continue;
      }

      const acqDate = toDateStr(acq.acquisitionDate);
      if (dateInRange(acqDate, windowStart, windowEnd)) {
        replacementLotId = acq.lotId ?? acq.id ?? null;
        break; // first match is sufficient
      }
    }

    if (replacementLotId !== null) {
      windows.push({
        token,
        saleDate,
        windowStart,
        windowEnd,
        disallowedLoss: lossAmount,
        replacementLotId,
        disposalTxHash: disposal.txHash ?? null,
      });
    }
  }

  return windows;
}

/**
 * Filter wash sale windows to only those that are currently active
 * for a specific token.
 *
 * @param token - token symbol (case-insensitive)
 * @param asOfDate - the date to check against (ISO date string)
 * @param windows - all known wash sale windows
 * @returns List of active WashSaleWindow objects for the given token.
 */
export function getActiveWindows(
  token: string,
  asOfDate: string,
  windows: WashSaleWindow[],
): WashSaleWindow[] {
  const tokenUpper = token.toUpperCase();
  return windows.filter(
    (w) => w.token === tokenUpper && isWindowActive(w, asOfDate),
  );
}

/**
 * Adjust the cost basis of the replacement lot for a wash sale.
 *
 * The disallowed loss is added to the cost basis of the replacement lot,
 * effectively deferring the loss recognition until the replacement lot
 * is eventually disposed of.
 *
 * @param window - the WashSaleWindow with the disallowed loss
 * @param replacementLot - the TaxLot whose basis should be adjusted
 * @returns A new TaxLot with adjusted costBasisUsd.
 */
export function adjustBasisForWashSale(
  window: WashSaleWindow,
  replacementLot: TaxLot,
): TaxLot {
  return {
    ...replacementLot,
    costBasisUsd: replacementLot.costBasisUsd.plus(window.disallowedLoss),
  };
}

/**
 * Pre-sale check: would selling this token on the proposed date trigger
 * a wash sale based on recent acquisitions?
 *
 * @param token - token symbol
 * @param proposedSaleDate - the date the user wants to sell (ISO date string)
 * @param acquisitions - list of acquisition dicts with token, acquisitionDate
 * @returns WashSaleWarning if wash sale would be triggered, else null.
 */
export function wouldTriggerWashSale(
  token: string,
  proposedSaleDate: string,
  acquisitions: WashSaleAcquisitionInput[],
): WashSaleWarning | null {
  const tokenUpper = token.toUpperCase();
  const windowStart = addDays(proposedSaleDate, -WASH_SALE_WINDOW);
  const windowEnd = addDays(proposedSaleDate, WASH_SALE_WINDOW);

  for (const acq of acquisitions) {
    if (acq.token.toUpperCase() !== tokenUpper) {
      continue;
    }

    const acqDate = toDateStr(acq.acquisitionDate);
    if (dateInRange(acqDate, windowStart, windowEnd)) {
      return {
        warning: true,
        token: tokenUpper,
        acquisitionDate: acqDate,
        saleDate: proposedSaleDate,
        windowStart,
        windowEnd,
        lotId: acq.lotId ?? acq.id ?? null,
      };
    }
  }

  return null;
}
