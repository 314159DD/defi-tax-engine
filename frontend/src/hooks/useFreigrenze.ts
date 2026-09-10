'use client'

/**
 * React hook for German Freigrenze (EUR 1,000 tax-free threshold) tracking.
 *
 * Calculates year-to-date short-term gains vs the EUR 1,000 cliff limit.
 * IMPORTANT: This is a cliff, not a deduction. If total >= EUR 1,000,
 * ALL short-term gains are fully taxable.
 *
 * Reference: section 23 Abs. 3 Satz 5 EStG
 *
 * Sprint C.6
 */

import { useMemo } from 'react'
import Decimal from 'decimal.js'
import type { SerializedDisposal } from '@/engine'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FreigrenzeStatus = 'safe' | 'warning' | 'exceeded'

export interface FreigrenzeResult {
  /** Total short-term gains realized YTD (Decimal string). */
  currentGains: string
  /** The EUR 1,000 limit (Decimal string). */
  limit: string
  /** Remaining headroom before cliff (Decimal string). */
  remaining: string
  /** Whether total >= 1,000 EUR. */
  exceeded: boolean
  /** 'safe' (<800), 'warning' (800-999.99), 'exceeded' (>=1000). */
  status: FreigrenzeStatus
  /** Percentage of limit consumed (0-100+). */
  percentUsed: number
  /** Number of short-term disposals counted. */
  disposalCount: number
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FREIGRENZE_LIMIT = new Decimal('1000')
const WARNING_THRESHOLD = new Decimal('800')
const ZERO = new Decimal('0')

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isShortTerm(d: SerializedDisposal): boolean {
  const hp = d.holdingPeriod
  return hp === 'short-term' || hp === 'short' || hp === 'SHORT_TERM'
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Track German Freigrenze status for a given tax year.
 *
 * @param disposals - Serialized disposals (from worker result)
 * @param year - Tax year to filter on
 * @returns Freigrenze status with current gains, remaining, and status
 */
export function useFreigrenze(
  disposals: SerializedDisposal[],
  year: number,
): FreigrenzeResult {
  return useMemo(() => {
    // Filter to the requested year and short-term only
    let totalShortTermGains = ZERO
    let count = 0

    for (const d of disposals) {
      const dYear = new Date(d.date).getFullYear()
      if (dYear !== year) continue
      if (!isShortTerm(d)) continue

      const gain = new Decimal(d.gainLossUsd)
      if (gain.gt(ZERO)) {
        totalShortTermGains = totalShortTermGains.plus(gain)
        count++
      }
    }

    const remaining = Decimal.max(FREIGRENZE_LIMIT.minus(totalShortTermGains), ZERO)
    const exceeded = totalShortTermGains.gte(FREIGRENZE_LIMIT)

    let status: FreigrenzeStatus
    if (exceeded) {
      status = 'exceeded'
    } else if (totalShortTermGains.gte(WARNING_THRESHOLD)) {
      status = 'warning'
    } else {
      status = 'safe'
    }

    const percentUsed = FREIGRENZE_LIMIT.isZero()
      ? 0
      : totalShortTermGains.div(FREIGRENZE_LIMIT).times(100).toNumber()

    return {
      currentGains: totalShortTermGains.toString(),
      limit: FREIGRENZE_LIMIT.toString(),
      remaining: remaining.toString(),
      exceeded,
      status,
      percentUsed: Math.round(percentUsed * 100) / 100,
      disposalCount: count,
    }
  }, [disposals, year])
}
