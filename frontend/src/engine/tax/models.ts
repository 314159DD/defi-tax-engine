/**
 * Tax-specific model re-exports and additional types.
 *
 * Re-exports core types from ../types.ts so that tax module code can
 * import from a single location. Add any tax-only types here that
 * don't belong in the core engine types.
 *
 * Ported from: src/tax/models.py
 */

// Re-export everything tax modules need from the core types
export {
  HoldingPeriod,
  type Exemption,
  type TaxSummary,
  type ReportFile,
  type IncomeCategory,
  type Disposal,
  type TaxLot,
  type LotConsumption,
  createExemption,
  createTaxSummary,
  ensureDecimal,
} from '../types';

// Re-export the TaxModule interface
export type { TaxModule } from './base';
