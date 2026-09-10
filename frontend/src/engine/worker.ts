/**
 * Web Worker entry point for the crypto-tax compute engine.
 *
 * All heavy computation (categorization, cost basis calculation, report
 * generation) runs off the main thread to keep the UI responsive.
 */

/// <reference lib="webworker" />

import type {
  WorkerRequest,
  WorkerResponse,
  CalculateRequest,
  CompareRequest,
  ReportRequest,
  CategorizeRequest,
  ParseCsvRequest,
  SpekulationsfristRequest,
  FreigrenzeRequest,
} from './worker-types';
import {
  deserializeTransaction,
  deserializeDisposal,
  deserializeTaxLot,
  serializeTransaction,
  serializeDisposal,
  serializeTaxLot,
  serializeTaxSummary,
  serializeExemption,
} from './types';
import type { Disposal, Transaction, TaxLot } from './types';
import { HoldingPeriod } from './types';
import { CalculatorEngine } from './calculator/engine';
import { categorizeTransactions } from './categorizer/engine';
import { USTaxModule } from './tax/us/module';
import { GermanTaxModule } from './tax/de/module';
import type { TaxModule } from './tax/base';
import { parseExchangeCsv } from './parsers/index';
import { generateForm8949 } from './tax/us/form8949';
import { generateScheduleD } from './tax/us/schedule-d';
import { generateTurboTaxExport } from './tax/us/turbotax';
import { generateIncomeReport } from './tax/us/income-report';
import { generateAnlageSO } from './tax/de/anlage-so';
import { generateWisoExport } from './tax/de/wiso';
import { generateDatevExport } from './tax/de/datev';
import type { IncomeEvent } from './tax/us/income-report';
import Decimal from 'decimal.js';

const ctx = self as unknown as DedicatedWorkerGlobalScope;

function postResponse(response: WorkerResponse): void {
  ctx.postMessage(response);
}

function postProgress(percent: number, message: string): void {
  postResponse({ type: 'progress', percent, message });
}

function postError(message: string): void {
  postResponse({ type: 'error', message });
}

// ---------------------------------------------------------------------------
// Tax module factory
// ---------------------------------------------------------------------------

/** Convert Transaction[] income events to the IncomeEvent[] format report generators expect. */
function toIncomeEvents(txs: Transaction[]): IncomeEvent[] {
  const events: IncomeEvent[] = [];
  for (const tx of txs) {
    if (tx.txType !== 'reward' && tx.txType !== 'airdrop') continue;
    for (const a of tx.assetsIn) {
      events.push({
        date: tx.timestamp,
        txType: tx.txType,
        token: a.tokenSymbol,
        amount: a.amount.toString(),
        usdValue: (a.usdValue ?? new Decimal('0')).toString(),
        txHash: tx.txHash,
        chain: tx.chain,
      });
    }
  }
  return events;
}

function getTaxModule(country: 'US' | 'DE'): TaxModule {
  return country === 'DE' ? new GermanTaxModule() : new USTaxModule();
}

// ---------------------------------------------------------------------------
// Handler: categorize
// ---------------------------------------------------------------------------

function handleCategorize(req: CategorizeRequest): void {
  postProgress(10, 'Deserializing transactions...');
  const transactions = req.transactions.map(deserializeTransaction);

  postProgress(30, `Categorizing ${transactions.length} transactions...`);
  const walletSet = new Set(req.knownWallets.map((w) => w.toLowerCase()));
  const categorized = categorizeTransactions(transactions, walletSet);

  postProgress(90, 'Serializing results...');
  postResponse({
    type: 'categorize-result',
    transactions: categorized.map(serializeTransaction),
  });
}

// ---------------------------------------------------------------------------
// Handler: calculate
// ---------------------------------------------------------------------------

function handleCalculate(req: CalculateRequest): void {
  postProgress(5, 'Deserializing transactions...');
  const transactions = req.transactions.map(deserializeTransaction);

  postProgress(15, `Calculating ${req.method} cost basis for ${transactions.length} transactions...`);
  const engine = new CalculatorEngine(transactions, req.method, req.knownWallets);
  const result = engine.calculate(req.year);

  postProgress(70, 'Applying tax rules...');
  const taxModule = getTaxModule(req.country);
  const year = req.year ?? new Date().getFullYear();

  // Classify holding periods and tag citations
  let disposals: Disposal[] = result.disposals.map((d) => {
    const acquired = new Date(d.lotsConsumed[0]?.acquisitionDate ?? d.date);
    const disposed = new Date(d.date);
    const hp = taxModule.classifyHoldingPeriod(acquired, disposed);
    return { ...d, holdingPeriod: hp as string };
  });
  disposals = taxModule.tagCitations(disposals, year);

  // Apply exemptions
  const exemptions = taxModule.getExemptions(disposals, year);

  // Recalculate summary with tax module
  const summary = result.summary;
  const incomeEvents = transactions.filter(
    (tx) => tx.txType === 'reward' || tx.txType === 'airdrop',
  );
  let incomeTotal = new Decimal('0');
  for (const ie of incomeEvents) {
    for (const a of ie.assetsIn) {
      if (a.usdValue) incomeTotal = incomeTotal.plus(a.usdValue);
    }
  }
  summary.incomeTotal = incomeTotal;
  summary.exemptions = exemptions;
  summary.taxLiability = taxModule.calculateLiability(
    summary.totalGains,
    incomeTotal,
  );

  postProgress(95, 'Serializing results...');
  postResponse({
    type: 'calculate-result',
    disposals: disposals.map(serializeDisposal),
    lots: result.lots.map(serializeTaxLot),
    summary: serializeTaxSummary(summary),
  });
}

// ---------------------------------------------------------------------------
// Handler: compare
// ---------------------------------------------------------------------------

function handleCompare(req: CompareRequest): void {
  const transactions = req.transactions.map(deserializeTransaction);
  const taxModule = getTaxModule(req.country);
  const methods = taxModule.getCostBasisMethods();
  const comparison: Record<string, ReturnType<typeof serializeTaxSummary>> = {};

  for (let i = 0; i < methods.length; i++) {
    const method = methods[i] as 'FIFO' | 'LIFO' | 'HIFO';
    postProgress(
      Math.round(((i + 1) / methods.length) * 80),
      `Calculating ${method}...`,
    );

    const engine = new CalculatorEngine(transactions, method, req.knownWallets);
    const result = engine.calculate(req.year);

    let disposals: Disposal[] = result.disposals.map((d) => {
      const acquired = new Date(d.lotsConsumed[0]?.acquisitionDate ?? d.date);
      const disposed = new Date(d.date);
      const hp = taxModule.classifyHoldingPeriod(acquired, disposed);
      return { ...d, holdingPeriod: hp as string };
    });
    disposals = taxModule.tagCitations(disposals, req.year);
    const exemptions = taxModule.getExemptions(disposals, req.year);

    const summary = result.summary;
    summary.exemptions = exemptions;
    summary.taxLiability = taxModule.calculateLiability(
      summary.totalGains,
      summary.incomeTotal,
    );
    comparison[method] = serializeTaxSummary(summary);
  }

  postProgress(95, 'Done comparing methods');
  postResponse({ type: 'compare-result', comparison });
}

// ---------------------------------------------------------------------------
// Handler: report
// ---------------------------------------------------------------------------

function handleReport(req: ReportRequest): void {
  postProgress(10, `Generating ${req.reportType} report...`);

  const disposals = req.disposals.map(deserializeDisposal);
  const incomeEventsRaw = req.incomeEvents.map(deserializeTransaction);
  const incomeEvents = toIncomeEvents(incomeEventsRaw);

  const files: Array<{ filename: string; content: string; mimeType: string }> = [];

  // Determine which generator to use
  if (req.country === 'US') {
    switch (req.reportType) {
      case 'form8949': {
        const f = generateForm8949(disposals, req.year);
        files.push({ filename: f.filename, content: f.content, mimeType: f.mimeType });
        break;
      }
      case 'schedule-d': {
        const f = generateScheduleD(disposals, req.year);
        files.push({ filename: f.filename, content: f.content, mimeType: f.mimeType });
        break;
      }
      case 'turbotax': {
        const f = generateTurboTaxExport(disposals, req.year);
        files.push({ filename: f.filename, content: f.content, mimeType: f.mimeType });
        break;
      }
      case 'income': {
        const f = generateIncomeReport(incomeEvents, req.year);
        files.push({ filename: f.filename, content: f.content, mimeType: f.mimeType });
        break;
      }
      default:
        postError(`Unknown US report type: ${req.reportType}`);
        return;
    }
  } else if (req.country === 'DE') {
    switch (req.reportType) {
      case 'anlage-so': {
        const f = generateAnlageSO(disposals, incomeEvents, req.year);
        files.push({ filename: f.filename, content: f.content, mimeType: f.mimeType });
        break;
      }
      case 'wiso': {
        const f = generateWisoExport(disposals, req.year);
        files.push({ filename: f.filename, content: f.content, mimeType: f.mimeType });
        break;
      }
      case 'datev': {
        const f = generateDatevExport(disposals, req.year);
        files.push({ filename: f.filename, content: f.content, mimeType: f.mimeType });
        break;
      }
      default:
        postError(`Unknown DE report type: ${req.reportType}`);
        return;
    }
  } else {
    postError(`Unsupported country: ${req.country}`);
    return;
  }

  postProgress(100, 'Report generated');
  postResponse({ type: 'report-result', files });
}

// ---------------------------------------------------------------------------
// Handler: parse-csv
// ---------------------------------------------------------------------------

function handleParseCsv(req: ParseCsvRequest): void {
  postProgress(10, 'Parsing CSV...');

  const format = (req.format || undefined) as Parameters<typeof parseExchangeCsv>[1];
  const transactions = parseExchangeCsv(req.csvText, format);

  postProgress(90, `Parsed ${transactions.length} transactions`);
  postResponse({
    type: 'parse-csv-result',
    transactions: transactions.map(serializeTransaction),
  });
}

// ---------------------------------------------------------------------------
// Handler: spekulationsfrist
// ---------------------------------------------------------------------------

function handleSpekulationsfrist(req: SpekulationsfristRequest): void {
  postProgress(10, 'Analyzing Spekulationsfrist...');

  const lots = req.lots.map(deserializeTaxLot);
  const now = new Date();
  const MS_PER_DAY = 86_400_000;

  const results = lots
    .filter((lot) => lot.remaining.greaterThan(0))
    .map((lot) => {
      const acquired = new Date(lot.acquisitionDate);
      // Spekulationsfrist ends after 365 days (>365 = exempt)
      const endDate = new Date(acquired.getTime() + 366 * MS_PER_DAY);
      const daysRemaining = Math.max(
        0,
        Math.ceil((endDate.getTime() - now.getTime()) / MS_PER_DAY),
      );
      const isExempt = daysRemaining === 0;

      return {
        lotId: lot.id,
        token: lot.token,
        amount: lot.remaining.toString(),
        acquisitionDate: lot.acquisitionDate,
        spekulationsfristEnd: endDate.toISOString().slice(0, 10),
        isExempt,
        daysRemaining,
      };
    });

  postProgress(100, 'Spekulationsfrist analysis complete');
  postResponse({ type: 'spekulationsfrist-result', lots: results });
}

// ---------------------------------------------------------------------------
// Handler: freigrenze
// ---------------------------------------------------------------------------

function handleFreigrenze(req: FreigrenzeRequest): void {
  postProgress(10, 'Checking Freigrenze...');

  const disposals = req.disposals.map(deserializeDisposal);
  const FREIGRENZE = new Decimal('1000');

  // Sum short-term gains for the requested year
  let totalShortTermGains = new Decimal('0');
  const yearDisposals = disposals.filter((d) => {
    const dYear = parseInt(d.date.slice(0, 4), 10);
    return dYear === req.year;
  });

  for (const d of yearDisposals) {
    if (d.holdingPeriod === 'short-term' && d.gainLossUsd.greaterThan(0)) {
      totalShortTermGains = totalShortTermGains.plus(d.gainLossUsd);
    }
  }

  const isUnderLimit = totalShortTermGains.lessThan(FREIGRENZE);

  // Build exemptions list - if under limit, each short-term gain is exempt
  const exemptions = isUnderLimit
    ? yearDisposals
        .filter((d) => d.holdingPeriod === 'short-term' && d.gainLossUsd.greaterThan(0))
        .map((d) => ({
          disposalId: d.id,
          reason: 'Freigrenze §23 Abs. 3 Satz 5 EStG',
          citationCode: 'DE_FREIGRENZE',
          citationText: `Short-term gains under ${FREIGRENZE} EUR threshold`,
          exemptAmount: d.gainLossUsd.toString(),
        }))
    : [];

  postProgress(100, 'Freigrenze check complete');
  postResponse({
    type: 'freigrenze-result',
    data: {
      year: req.year,
      totalShortTermGains: totalShortTermGains.toString(),
      freigrenzeLimit: FREIGRENZE.toString(),
      isUnderLimit,
      exemptions,
    },
  });
}

// ---------------------------------------------------------------------------
// Message dispatcher
// ---------------------------------------------------------------------------

ctx.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const req = event.data;

  try {
    switch (req.type) {
      case 'categorize':
        handleCategorize(req);
        break;
      case 'calculate':
        handleCalculate(req);
        break;
      case 'compare':
        handleCompare(req);
        break;
      case 'report':
        handleReport(req);
        break;
      case 'parse-csv':
        handleParseCsv(req);
        break;
      case 'spekulationsfrist':
        handleSpekulationsfrist(req);
        break;
      case 'freigrenze':
        handleFreigrenze(req);
        break;
      default:
        postError(`Unknown request type: ${(req as { type: string }).type}`);
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    postError(message);
  }
};

// Signal that the worker is ready
postProgress(100, 'Worker initialized');
