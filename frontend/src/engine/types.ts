/**
 * Core type system for the crypto-tax client-side compute engine.
 *
 * Ported from Python dataclasses:
 *   - src/importers/models.py  (Transaction, AssetTransfer)
 *   - src/calculator/lots.py   (TaxLot, LotConsumption, Disposal)
 *   - src/tax/models.py        (HoldingPeriod, Exemption, TaxSummary, ReportFile, IncomeCategory)
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

import Decimal from 'decimal.js';

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

/** Coerce unknown value to Decimal. Throws on incompatible input. */
export function ensureDecimal(v: unknown): Decimal {
  if (v instanceof Decimal) return v;
  if (typeof v === 'string' || typeof v === 'number') return new Decimal(v);
  throw new TypeError(`Expected Decimal-compatible value, got ${typeof v}: ${v}`);
}

/** Coerce to Decimal or null. */
export function ensureDecimalOrNull(v: unknown): Decimal | null {
  if (v === null || v === undefined) return null;
  return ensureDecimal(v);
}

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export enum HoldingPeriod {
  SHORT_TERM = 'short-term',
  LONG_TERM = 'long-term',
  EXEMPT = 'exempt',
}

// ---------------------------------------------------------------------------
// Core interfaces (runtime - Decimal fields)
// ---------------------------------------------------------------------------

/** A single asset movement within a transaction. */
export interface AssetTransfer {
  tokenSymbol: string;
  amount: Decimal;
  tokenAddress: string | null;
  usdValue: Decimal | null;
}

/**
 * Normalized transaction model across all chains.
 *
 * txType values:
 *   transfer, swap, lp_add, lp_remove, stake, unstake, reward,
 *   bridge, airdrop, mint, burn, approve, unknown
 */
export interface Transaction {
  txHash: string;
  chain: string;
  blockNumber: number;
  timestamp: string; // ISO 8601
  fromAddress: string;
  toAddress: string;
  txType: string;
  assetsIn: AssetTransfer[];
  assetsOut: AssetTransfer[];
  fee: AssetTransfer | null;
  protocol: string | null;
  rawData: Record<string, unknown>;
}

/** A single acquisition lot. */
export interface TaxLot {
  id: string;
  token: string;
  amount: Decimal;
  costBasisUsd: Decimal;
  acquisitionDate: string; // ISO date
  remaining: Decimal;
  source: string;
  txHash: string;
  spekulationsfristEnd: string | null; // ISO date, for DE
}

/** Records which portion of a lot was consumed in a disposal. */
export interface LotConsumption {
  lotId: string;
  token: string;
  amountConsumed: Decimal;
  costBasisConsumed: Decimal;
  acquisitionDate: string; // ISO
}

/** A realized gain/loss event. */
export interface Disposal {
  id: string;
  date: string; // ISO
  token: string;
  amount: Decimal;
  proceedsUsd: Decimal;
  costBasisUsd: Decimal;
  gainLossUsd: Decimal;
  holdingPeriod: string; // 'short-term' | 'long-term' | 'exempt'
  method: string; // 'FIFO' | 'LIFO' | 'HIFO'
  lotsConsumed: LotConsumption[];
  txHash: string;
  exemption: Exemption | null;
  holdingPeriodEnum: HoldingPeriod | null;
  // Citation fields
  citationCode: string | null;
  citationText: string | null;
  citationSource: string | null;
  isGrayArea: boolean;
}

/** A tax exemption applied to a specific disposal. */
export interface Exemption {
  disposalId: string;
  reason: string;
  citationCode: string;
  citationText: string;
  exemptAmount: Decimal;
}

/** Aggregated tax calculation result for a given year + country. */
export interface TaxSummary {
  totalGains: Decimal;
  totalLosses: Decimal;
  net: Decimal;
  shortTermGains: Decimal;
  longTermGains: Decimal;
  exemptGains: Decimal;
  taxLiability: Decimal;
  exemptions: Exemption[];
  incomeTotal: Decimal;
}

/** A generated report file ready for download. */
export interface ReportFile {
  filename: string;
  content: string;
  mimeType: string;
  reportType: string;
}

/** Describes a category of taxable income and its legal basis. */
export interface IncomeCategory {
  name: string;
  description: string;
  citation: string;
}

// ---------------------------------------------------------------------------
// Factory functions (accept raw/loose input, produce strict types)
// ---------------------------------------------------------------------------

export function createAssetTransfer(raw: {
  tokenSymbol: string;
  amount: string | number | Decimal;
  tokenAddress?: string | null;
  usdValue?: string | number | Decimal | null;
}): AssetTransfer {
  return {
    tokenSymbol: raw.tokenSymbol,
    amount: ensureDecimal(raw.amount),
    tokenAddress: raw.tokenAddress ?? null,
    usdValue: ensureDecimalOrNull(raw.usdValue ?? null),
  };
}

export function createTransaction(raw: {
  txHash: string;
  chain: string;
  blockNumber: number;
  timestamp: string;
  fromAddress: string;
  toAddress: string;
  txType: string;
  assetsIn: Array<{
    tokenSymbol: string;
    amount: string | number | Decimal;
    tokenAddress?: string | null;
    usdValue?: string | number | Decimal | null;
  }>;
  assetsOut: Array<{
    tokenSymbol: string;
    amount: string | number | Decimal;
    tokenAddress?: string | null;
    usdValue?: string | number | Decimal | null;
  }>;
  fee?: {
    tokenSymbol: string;
    amount: string | number | Decimal;
    tokenAddress?: string | null;
    usdValue?: string | number | Decimal | null;
  } | null;
  protocol?: string | null;
  rawData?: Record<string, unknown>;
}): Transaction {
  return {
    txHash: raw.txHash,
    chain: raw.chain,
    blockNumber: raw.blockNumber,
    timestamp: raw.timestamp,
    fromAddress: raw.fromAddress,
    toAddress: raw.toAddress,
    txType: raw.txType,
    assetsIn: raw.assetsIn.map(createAssetTransfer),
    assetsOut: raw.assetsOut.map(createAssetTransfer),
    fee: raw.fee ? createAssetTransfer(raw.fee) : null,
    protocol: raw.protocol ?? null,
    rawData: raw.rawData ?? {},
  };
}

export function createTaxLot(raw: {
  id: string;
  token: string;
  amount: string | number | Decimal;
  costBasisUsd: string | number | Decimal;
  acquisitionDate: string;
  remaining: string | number | Decimal;
  source: string;
  txHash: string;
  spekulationsfristEnd?: string | null;
}): TaxLot {
  return {
    id: raw.id,
    token: raw.token,
    amount: ensureDecimal(raw.amount),
    costBasisUsd: ensureDecimal(raw.costBasisUsd),
    acquisitionDate: raw.acquisitionDate,
    remaining: ensureDecimal(raw.remaining),
    source: raw.source,
    txHash: raw.txHash,
    spekulationsfristEnd: raw.spekulationsfristEnd ?? null,
  };
}

export function createLotConsumption(raw: {
  lotId: string;
  token: string;
  amountConsumed: string | number | Decimal;
  costBasisConsumed: string | number | Decimal;
  acquisitionDate: string;
}): LotConsumption {
  return {
    lotId: raw.lotId,
    token: raw.token,
    amountConsumed: ensureDecimal(raw.amountConsumed),
    costBasisConsumed: ensureDecimal(raw.costBasisConsumed),
    acquisitionDate: raw.acquisitionDate,
  };
}

export function createDisposal(raw: {
  id: string;
  date: string;
  token: string;
  amount: string | number | Decimal;
  proceedsUsd: string | number | Decimal;
  costBasisUsd: string | number | Decimal;
  gainLossUsd: string | number | Decimal;
  holdingPeriod: string;
  method: string;
  lotsConsumed?: Array<{
    lotId: string;
    token: string;
    amountConsumed: string | number | Decimal;
    costBasisConsumed: string | number | Decimal;
    acquisitionDate: string;
  }>;
  txHash: string;
  exemption?: Exemption | null;
  holdingPeriodEnum?: HoldingPeriod | null;
  citationCode?: string | null;
  citationText?: string | null;
  citationSource?: string | null;
  isGrayArea?: boolean;
}): Disposal {
  return {
    id: raw.id,
    date: raw.date,
    token: raw.token,
    amount: ensureDecimal(raw.amount),
    proceedsUsd: ensureDecimal(raw.proceedsUsd),
    costBasisUsd: ensureDecimal(raw.costBasisUsd),
    gainLossUsd: ensureDecimal(raw.gainLossUsd),
    holdingPeriod: raw.holdingPeriod,
    method: raw.method,
    lotsConsumed: (raw.lotsConsumed ?? []).map(createLotConsumption),
    txHash: raw.txHash,
    exemption: raw.exemption ?? null,
    holdingPeriodEnum: raw.holdingPeriodEnum ?? null,
    citationCode: raw.citationCode ?? null,
    citationText: raw.citationText ?? null,
    citationSource: raw.citationSource ?? null,
    isGrayArea: raw.isGrayArea ?? false,
  };
}

export function createExemption(raw: {
  disposalId: string;
  reason: string;
  citationCode: string;
  citationText: string;
  exemptAmount?: string | number | Decimal;
}): Exemption {
  return {
    disposalId: raw.disposalId,
    reason: raw.reason,
    citationCode: raw.citationCode,
    citationText: raw.citationText,
    exemptAmount: ensureDecimal(raw.exemptAmount ?? '0'),
  };
}

export function createTaxSummary(raw: {
  totalGains?: string | number | Decimal;
  totalLosses?: string | number | Decimal;
  net?: string | number | Decimal;
  shortTermGains?: string | number | Decimal;
  longTermGains?: string | number | Decimal;
  exemptGains?: string | number | Decimal;
  taxLiability?: string | number | Decimal;
  exemptions?: Exemption[];
  incomeTotal?: string | number | Decimal;
}): TaxSummary {
  return {
    totalGains: ensureDecimal(raw.totalGains ?? '0'),
    totalLosses: ensureDecimal(raw.totalLosses ?? '0'),
    net: ensureDecimal(raw.net ?? '0'),
    shortTermGains: ensureDecimal(raw.shortTermGains ?? '0'),
    longTermGains: ensureDecimal(raw.longTermGains ?? '0'),
    exemptGains: ensureDecimal(raw.exemptGains ?? '0'),
    taxLiability: ensureDecimal(raw.taxLiability ?? '0'),
    exemptions: raw.exemptions ?? [],
    incomeTotal: ensureDecimal(raw.incomeTotal ?? '0'),
  };
}

// ---------------------------------------------------------------------------
// Serialized types (Worker boundary - Decimal → string)
// ---------------------------------------------------------------------------

export interface SerializedAssetTransfer {
  tokenSymbol: string;
  amount: string;
  tokenAddress: string | null;
  usdValue: string | null;
}

export interface SerializedTransaction {
  txHash: string;
  chain: string;
  blockNumber: number;
  timestamp: string;
  fromAddress: string;
  toAddress: string;
  txType: string;
  assetsIn: SerializedAssetTransfer[];
  assetsOut: SerializedAssetTransfer[];
  fee: SerializedAssetTransfer | null;
  protocol: string | null;
  rawData: Record<string, unknown>;
}

export interface SerializedTaxLot {
  id: string;
  token: string;
  amount: string;
  costBasisUsd: string;
  acquisitionDate: string;
  remaining: string;
  source: string;
  txHash: string;
  spekulationsfristEnd: string | null;
}

export interface SerializedLotConsumption {
  lotId: string;
  token: string;
  amountConsumed: string;
  costBasisConsumed: string;
  acquisitionDate: string;
}

export interface SerializedDisposal {
  id: string;
  date: string;
  token: string;
  amount: string;
  proceedsUsd: string;
  costBasisUsd: string;
  gainLossUsd: string;
  holdingPeriod: string;
  method: string;
  lotsConsumed: SerializedLotConsumption[];
  txHash: string;
  exemption: SerializedExemption | null;
  holdingPeriodEnum: HoldingPeriod | null;
  citationCode: string | null;
  citationText: string | null;
  citationSource: string | null;
  isGrayArea: boolean;
}

export interface SerializedExemption {
  disposalId: string;
  reason: string;
  citationCode: string;
  citationText: string;
  exemptAmount: string;
}

export interface SerializedTaxSummary {
  totalGains: string;
  totalLosses: string;
  net: string;
  shortTermGains: string;
  longTermGains: string;
  exemptGains: string;
  taxLiability: string;
  exemptions: SerializedExemption[];
  incomeTotal: string;
}

// ---------------------------------------------------------------------------
// Serialization helpers
// ---------------------------------------------------------------------------

function serializeAssetTransfer(t: AssetTransfer): SerializedAssetTransfer {
  return {
    tokenSymbol: t.tokenSymbol,
    amount: t.amount.toString(),
    tokenAddress: t.tokenAddress,
    usdValue: t.usdValue?.toString() ?? null,
  };
}

function deserializeAssetTransfer(raw: SerializedAssetTransfer): AssetTransfer {
  return createAssetTransfer(raw);
}

export function serializeTransaction(tx: Transaction): SerializedTransaction {
  return {
    txHash: tx.txHash,
    chain: tx.chain,
    blockNumber: tx.blockNumber,
    timestamp: tx.timestamp,
    fromAddress: tx.fromAddress,
    toAddress: tx.toAddress,
    txType: tx.txType,
    assetsIn: tx.assetsIn.map(serializeAssetTransfer),
    assetsOut: tx.assetsOut.map(serializeAssetTransfer),
    fee: tx.fee ? serializeAssetTransfer(tx.fee) : null,
    protocol: tx.protocol,
    rawData: tx.rawData,
  };
}

export function deserializeTransaction(raw: SerializedTransaction): Transaction {
  return createTransaction({
    ...raw,
    assetsIn: raw.assetsIn.map(deserializeAssetTransfer),
    assetsOut: raw.assetsOut.map(deserializeAssetTransfer),
    fee: raw.fee ? deserializeAssetTransfer(raw.fee) : null,
  });
}

export function serializeExemption(e: Exemption): SerializedExemption {
  return {
    disposalId: e.disposalId,
    reason: e.reason,
    citationCode: e.citationCode,
    citationText: e.citationText,
    exemptAmount: e.exemptAmount.toString(),
  };
}

export function deserializeExemption(raw: SerializedExemption): Exemption {
  return createExemption(raw);
}

function serializeLotConsumption(lc: LotConsumption): SerializedLotConsumption {
  return {
    lotId: lc.lotId,
    token: lc.token,
    amountConsumed: lc.amountConsumed.toString(),
    costBasisConsumed: lc.costBasisConsumed.toString(),
    acquisitionDate: lc.acquisitionDate,
  };
}

function deserializeLotConsumption(raw: SerializedLotConsumption): LotConsumption {
  return createLotConsumption(raw);
}

export function serializeTaxLot(lot: TaxLot): SerializedTaxLot {
  return {
    id: lot.id,
    token: lot.token,
    amount: lot.amount.toString(),
    costBasisUsd: lot.costBasisUsd.toString(),
    acquisitionDate: lot.acquisitionDate,
    remaining: lot.remaining.toString(),
    source: lot.source,
    txHash: lot.txHash,
    spekulationsfristEnd: lot.spekulationsfristEnd,
  };
}

export function deserializeTaxLot(raw: SerializedTaxLot): TaxLot {
  return createTaxLot(raw);
}

export function serializeDisposal(d: Disposal): SerializedDisposal {
  return {
    id: d.id,
    date: d.date,
    token: d.token,
    amount: d.amount.toString(),
    proceedsUsd: d.proceedsUsd.toString(),
    costBasisUsd: d.costBasisUsd.toString(),
    gainLossUsd: d.gainLossUsd.toString(),
    holdingPeriod: d.holdingPeriod,
    method: d.method,
    lotsConsumed: d.lotsConsumed.map(serializeLotConsumption),
    txHash: d.txHash,
    exemption: d.exemption ? serializeExemption(d.exemption) : null,
    holdingPeriodEnum: d.holdingPeriodEnum,
    citationCode: d.citationCode,
    citationText: d.citationText,
    citationSource: d.citationSource,
    isGrayArea: d.isGrayArea,
  };
}

export function deserializeDisposal(raw: SerializedDisposal): Disposal {
  return {
    ...createDisposal({
      ...raw,
      lotsConsumed: raw.lotsConsumed.map(deserializeLotConsumption),
      exemption: raw.exemption ? deserializeExemption(raw.exemption) : null,
    }),
  };
}

export function serializeTaxSummary(s: TaxSummary): SerializedTaxSummary {
  return {
    totalGains: s.totalGains.toString(),
    totalLosses: s.totalLosses.toString(),
    net: s.net.toString(),
    shortTermGains: s.shortTermGains.toString(),
    longTermGains: s.longTermGains.toString(),
    exemptGains: s.exemptGains.toString(),
    taxLiability: s.taxLiability.toString(),
    exemptions: s.exemptions.map(serializeExemption),
    incomeTotal: s.incomeTotal.toString(),
  };
}

export function deserializeTaxSummary(raw: SerializedTaxSummary): TaxSummary {
  return {
    ...createTaxSummary({
      ...raw,
      exemptions: raw.exemptions.map(deserializeExemption),
    }),
  };
}
