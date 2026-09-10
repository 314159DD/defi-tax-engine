'use client'

/**
 * React hook for German Spekulationsfrist (1-year holding period) tracking.
 *
 * Computes per-lot holding status, sorted by soonest to become tax-exempt.
 * Uses the worker protocol for heavy computation, but can also compute
 * client-side for small lot counts.
 *
 * Sprint C.6
 */

import { useMemo } from 'react'
import type { SerializedTaxLot } from '@/engine'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SpekulationsfristLot {
  lotId: string
  token: string
  amount: string
  acquisitionDate: string
  spekulationsfristEnd: string
  isExempt: boolean
  daysRemaining: number
}

export interface SpekulationsfristSummary {
  lots: SpekulationsfristLot[]
  taxFreeCount: number
  approachingCount: number // within 30 days
  taxableCount: number
  totalLots: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MS_PER_DAY = 86_400_000

function daysBetween(a: Date, b: Date): number {
  const utcA = Date.UTC(a.getFullYear(), a.getMonth(), a.getDate())
  const utcB = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate())
  return Math.round((utcB - utcA) / MS_PER_DAY)
}

function computeSpekulationsfristEnd(acquisitionDate: string): Date {
  const acq = new Date(acquisitionDate.slice(0, 10) + 'T00:00:00Z')

  // End date = acquisition date + 1 year + 1 day (first exempt day)
  let endYear = acq.getUTCFullYear() + 1
  let endMonth = acq.getUTCMonth()
  let endDay = acq.getUTCDate()

  // Handle Feb 29 edge case: Feb 29 -> Mar 1 next year
  if (acq.getUTCMonth() === 1 && acq.getUTCDate() === 29) {
    endMonth = 2 // March (0-indexed)
    endDay = 1
  }

  return new Date(Date.UTC(endYear, endMonth, endDay))
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Compute Spekulationsfrist status for a list of tax lots.
 *
 * @param lots - Serialized tax lots (string amounts from worker boundary)
 * @param asOfDate - Optional ISO date to compute from (default: today)
 * @returns Summary with sorted lots and category counts
 */
export function useSpekulationsfrist(
  lots: SerializedTaxLot[],
  asOfDate?: string,
): SpekulationsfristSummary {
  return useMemo(() => {
    const today = asOfDate
      ? new Date(asOfDate.slice(0, 10) + 'T00:00:00Z')
      : new Date()

    const result: SpekulationsfristLot[] = []

    for (const lot of lots) {
      // Skip fully consumed lots
      if (lot.remaining === '0' || parseFloat(lot.remaining) <= 0) continue

      const endDate = computeSpekulationsfristEnd(lot.acquisitionDate)
      const endDateStr = endDate.toISOString().slice(0, 10)
      const daysRemaining = Math.max(daysBetween(today, endDate), 0)

      result.push({
        lotId: lot.id,
        token: lot.token,
        amount: lot.remaining,
        acquisitionDate: lot.acquisitionDate,
        spekulationsfristEnd: endDateStr,
        isExempt: daysRemaining === 0,
        daysRemaining,
      })
    }

    // Sort by days remaining ascending (soonest to exempt first)
    result.sort((a, b) => a.daysRemaining - b.daysRemaining)

    let taxFreeCount = 0
    let approachingCount = 0
    let taxableCount = 0

    for (const lot of result) {
      if (lot.isExempt) {
        taxFreeCount++
      } else if (lot.daysRemaining <= 30) {
        approachingCount++
      } else {
        taxableCount++
      }
    }

    return {
      lots: result,
      taxFreeCount,
      approachingCount,
      taxableCount,
      totalLots: result.length,
    }
  }, [lots, asOfDate])
}
