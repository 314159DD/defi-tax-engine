/**
 * Barrel export for the crypto-tax compute engine.
 *
 * Sprint C.6 - provides a single import surface for the entire engine.
 *
 * Usage:
 *   import { CalculatorEngine, USTaxModule, parseExchangeCsv } from '@/engine'
 *   import type { Transaction, TaxLot, WorkerRequest } from '@/engine'
 */

// ---------------------------------------------------------------------------
// Core types + serialization helpers
// ---------------------------------------------------------------------------

export * from './types'
export * from './worker-types'

// ---------------------------------------------------------------------------
// Tax modules
// ---------------------------------------------------------------------------

export { USTaxModule } from './tax/us/module'
export { GermanTaxModule } from './tax/de/module'
export type { TaxModule } from './tax/base'
export { getDefaultIncomeCategories } from './tax/base'

// ---------------------------------------------------------------------------
// Categorizer
// ---------------------------------------------------------------------------

export {
  CategorizerEngine,
  categorizeTransactions,
  isTaxableDisposal,
  isIncomeEvent,
  TAXABLE_TYPES,
  INCOME_TYPES,
  NON_TAXABLE_TYPES,
} from './categorizer/engine'

// ---------------------------------------------------------------------------
// Calculator
// ---------------------------------------------------------------------------

export { CalculatorEngine } from './calculator/engine'
export type { CalculateResult } from './calculator/engine'

// ---------------------------------------------------------------------------
// Parsers
// ---------------------------------------------------------------------------

export { parseExchangeCsv, detectFormat } from './parsers/index'
export type { ExchangeFormat } from './parsers/index'

// ---------------------------------------------------------------------------
// Reports - Harvest & Source of Funds
// ---------------------------------------------------------------------------

export { analyzeHarvest, getUnrealizedPositions, formatHarvestReport } from './reports/harvest'
export type { UnrealizedPosition, HarvestSuggestion, TaxLotInput } from './reports/harvest'

export { simulateHarvest, getFreigrenzeHeadroom } from './reports/harvest-simulator'
export type { HarvestScenario } from './reports/harvest-simulator'

export { traceHoldings, generateSourceOfFundsCsv, generateSourceOfFundsText } from './reports/source-of-funds'
export type { FundingStep, HoldingOrigin, SourceOfFundsReport } from './reports/source-of-funds'

// ---------------------------------------------------------------------------
// US reports
// ---------------------------------------------------------------------------

export { generateForm8949 } from './tax/us/form8949'
export { generateScheduleD } from './tax/us/schedule-d'
export { generateTurboTaxExport } from './tax/us/turbotax'
export { generateIncomeReport } from './tax/us/income-report'
export { reconcile } from './tax/us/reconciliation'

// ---------------------------------------------------------------------------
// DE reports
// ---------------------------------------------------------------------------

export { generateAnlageSO } from './tax/de/anlage-so'
export { generateWisoExport } from './tax/de/wiso'
export { generateDatevExport } from './tax/de/datev'
