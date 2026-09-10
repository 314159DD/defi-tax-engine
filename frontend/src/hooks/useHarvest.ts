'use client'

/**
 * React hook for tax loss harvesting analysis.
 *
 * Delegates computation to the engine functions (analyzeHarvest,
 * getUnrealizedPositions, simulateHarvest) running on the main thread
 * since these are fast lookups over already-computed lot data.
 *
 * Sprint C.6
 */

import { useCallback, useMemo, useState } from 'react'
import Decimal from 'decimal.js'
import {
  analyzeHarvest,
  getUnrealizedPositions,
  simulateHarvest,
} from '@/engine'
import type {
  TaxLotInput,
  UnrealizedPosition,
  HarvestSuggestion,
  HarvestScenario,
} from '@/engine'

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export interface HarvestState {
  positions: UnrealizedPosition[]
  suggestions: HarvestSuggestion[]
  scenario: HarvestScenario | null
  loading: boolean
  error: string | null
}

const INITIAL: HarvestState = {
  positions: [],
  suggestions: [],
  scenario: null,
  loading: false,
  error: null,
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseHarvestOptions {
  /** Open tax lots with remaining amounts. */
  lots: TaxLotInput[]
  /** Current prices: token symbol (uppercased) -> Decimal price. */
  currentPrices: Record<string, Decimal>
  /** "US" or "DE" */
  country?: string
  /** Recent purchases for wash sale detection: token -> ISO date strings. */
  recentPurchases?: Record<string, string[]>
  /** As-of date (ISO string). Default: today. */
  asOfDate?: string
}

export function useHarvest(options: UseHarvestOptions) {
  const {
    lots,
    currentPrices,
    country = 'US',
    recentPurchases = {},
    asOfDate,
  } = options

  const [state, setState] = useState<HarvestState>(INITIAL)

  // Compute positions + suggestions whenever inputs change
  const { positions, suggestions } = useMemo(() => {
    try {
      const pos = getUnrealizedPositions(lots, currentPrices, country, asOfDate)
      const sug = analyzeHarvest(
        lots,
        currentPrices,
        recentPurchases,
        undefined,
        undefined,
        asOfDate,
      )
      return { positions: pos, suggestions: sug }
    } catch (err) {
      return { positions: [] as UnrealizedPosition[], suggestions: [] as HarvestSuggestion[] }
    }
  }, [lots, currentPrices, country, recentPurchases, asOfDate])

  // Run a what-if harvest simulation on selected positions
  const simulate = useCallback(
    (
      selectedPositions: UnrealizedPosition[],
      currentYearGains: Decimal = new Decimal('0'),
      userBracket: Decimal = new Decimal('0.30'),
      selectedLotIds?: string[],
    ) => {
      setState((s) => ({ ...s, loading: true, error: null }))
      try {
        const scenario = simulateHarvest(
          selectedPositions,
          country,
          currentYearGains,
          userBracket,
          selectedLotIds,
        )
        setState((s) => ({
          ...s,
          scenario,
          loading: false,
        }))
        return scenario
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        setState((s) => ({ ...s, error: message, loading: false }))
        return null
      }
    },
    [country],
  )

  // Clear scenario
  const clearScenario = useCallback(() => {
    setState((s) => ({ ...s, scenario: null }))
  }, [])

  return {
    positions,
    suggestions,
    scenario: state.scenario,
    loading: state.loading,
    error: state.error,
    simulate,
    clearScenario,
  }
}
