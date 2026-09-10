/**
 * Worker message protocol for the crypto-tax compute engine.
 *
 * All types crossing the Worker boundary use serialized forms
 * (Decimal -> string) because structured-clone cannot handle Decimal instances.
 */

import type {
  SerializedDisposal,
  SerializedExemption,
  SerializedTaxLot,
  SerializedTaxSummary,
  SerializedTransaction,
} from './types';

// ---------------------------------------------------------------------------
// Requests (main thread -> worker)
// ---------------------------------------------------------------------------

export type WorkerRequest =
  | CategorizeRequest
  | CalculateRequest
  | CompareRequest
  | ReportRequest
  | ParseCsvRequest
  | SpekulationsfristRequest
  | FreigrenzeRequest;

export interface CategorizeRequest {
  type: 'categorize';
  transactions: SerializedTransaction[];
  knownWallets: string[];
}

export interface CalculateRequest {
  type: 'calculate';
  transactions: SerializedTransaction[];
  method: 'FIFO' | 'LIFO' | 'HIFO';
  year?: number;
  country: 'US' | 'DE';
  knownWallets: string[];
}

export interface CompareRequest {
  type: 'compare';
  transactions: SerializedTransaction[];
  year: number;
  country: 'US' | 'DE';
  knownWallets: string[];
}

export interface ReportRequest {
  type: 'report';
  disposals: SerializedDisposal[];
  incomeEvents: SerializedTransaction[];
  year: number;
  method: string;
  country: 'US' | 'DE';
  reportType: string;
}

export interface ParseCsvRequest {
  type: 'parse-csv';
  csvText: string;
  format: string;
}

export interface SpekulationsfristRequest {
  type: 'spekulationsfrist';
  lots: SerializedTaxLot[];
}

export interface FreigrenzeRequest {
  type: 'freigrenze';
  disposals: SerializedDisposal[];
  year: number;
}

// ---------------------------------------------------------------------------
// Responses (worker -> main thread)
// ---------------------------------------------------------------------------

export type WorkerResponse =
  | CategorizeResult
  | CalculateResult
  | CompareResult
  | ReportResult
  | ParseCsvResult
  | SpekulationsfristResult
  | FreigrenzeResult
  | ProgressMessage
  | ErrorMessage;

export interface CategorizeResult {
  type: 'categorize-result';
  transactions: SerializedTransaction[];
}

export interface CalculateResult {
  type: 'calculate-result';
  disposals: SerializedDisposal[];
  lots: SerializedTaxLot[];
  summary: SerializedTaxSummary;
}

export interface CompareResult {
  type: 'compare-result';
  comparison: Record<string, SerializedTaxSummary>;
}

export interface ReportResult {
  type: 'report-result';
  files: Array<{
    filename: string;
    content: string;
    mimeType: string;
  }>;
}

export interface ParseCsvResult {
  type: 'parse-csv-result';
  transactions: SerializedTransaction[];
}

export interface SpekulationsfristResult {
  type: 'spekulationsfrist-result';
  lots: Array<{
    lotId: string;
    token: string;
    amount: string;
    acquisitionDate: string;
    spekulationsfristEnd: string;
    isExempt: boolean;
    daysRemaining: number;
  }>;
}

export interface FreigrenzeResult {
  type: 'freigrenze-result';
  data: {
    year: number;
    totalShortTermGains: string;
    freigrenzeLimit: string;
    isUnderLimit: boolean;
    exemptions: SerializedExemption[];
  };
}

export interface ProgressMessage {
  type: 'progress';
  percent: number;
  message: string;
}

export interface ErrorMessage {
  type: 'error';
  message: string;
}
