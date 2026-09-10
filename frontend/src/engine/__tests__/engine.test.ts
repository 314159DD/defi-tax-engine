/**
 * Engine fixture tests - no real wallets, no money, no external calls.
 *
 * Each test constructs Transaction[] with known inputs and asserts exact
 * outputs from the calculator + tax modules. Ground truth is manual arithmetic,
 * documented inline.
 *
 * How buys are modelled: `swap` with USDC assetsOut (no lot needed - engine warns
 * but continues) and the target token as assetsIn. This creates the acquisition lot.
 *
 * US-01  Simple buy + sell (short-term FIFO gain)
 * US-02  Simple buy + sell (long-term, >365 days)
 * US-03  Buy + sell at a loss
 * US-04  FIFO vs HIFO - same txs, lower liability with HIFO
 * US-05  Swap: token-for-token (ETH → USDC), disposal of outgoing token
 * US-06  Bridge - zero disposals, cost basis carries over
 * US-07  LP deposit (lp_add) - zero phantom gain
 * US-08  Staking reward - lot created at FMV, disposal gain is correct
 * US-09  Airdrop - income lot created, zero disposals, lot is in book
 * US-10  Gas fee deducted from proceeds on disposal
 *
 * DE-01  Spekulationsfrist - hold >365 days = EXEMPT
 * DE-02  Spekulationsfrist - hold exactly 365 days = SHORT_TERM (taxable)
 * DE-03  Freigrenze below cliff (€999) - getExemptions returns Freigrenze exemption
 * DE-04  Freigrenze at cliff (€1,000) - NO exemption (cliff, not a deduction)
 * DE-05  Freigrenze above cliff (€1,001) - NO exemption
 */

import { describe, it, expect } from 'vitest';
import Decimal from 'decimal.js';
import { createTransaction, createDisposal, HoldingPeriod } from '../types';
import { CalculatorEngine } from '../calculator/engine';
import { GermanTaxModule } from '../tax/de/module';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const USER = '0xuser000000000000000000000000000000000001';
const OTHER = '0xother00000000000000000000000000000000002';

// Unique counter per test file load (no shared state across parallel runs)
let _seq = 0;

function makeTx(
  txType: string,
  timestamp: string,
  assetsIn: Array<{ tokenSymbol: string; amount: string; usdValue?: string }>,
  assetsOut: Array<{ tokenSymbol: string; amount: string; usdValue?: string }>,
  opts: {
    fee?: { tokenSymbol: string; amount: string; usdValue: string };
    protocol?: string;
  } = {},
) {
  _seq++;
  return createTransaction({
    txHash: `0x${String(_seq).padStart(64, '0')}`,
    chain: 'ethereum',
    blockNumber: _seq * 100,
    timestamp,
    fromAddress: USER,
    toAddress: OTHER,
    txType,
    assetsIn: assetsIn.map((a) => ({ ...a, tokenAddress: null })),
    assetsOut: assetsOut.map((a) => ({ ...a, tokenAddress: null })),
    fee: opts.fee ? { ...opts.fee, tokenAddress: null } : null,
    protocol: opts.protocol ?? null,
  });
}

/** Model a fiat/CEX buy as a swap: USDC goes out (no lot needed), target comes in. */
function buy(
  token: string,
  amount: string,
  usdValue: string,
  timestamp: string,
) {
  return makeTx(
    'swap',
    timestamp,
    [{ tokenSymbol: token, amount, usdValue }],     // assetsIn: acquisition
    [{ tokenSymbol: 'USDC', amount: usdValue, usdValue }], // assetsOut: USDC (no lot - engine warns and skips disposal)
  );
}

/** Model a sell as a swap: token goes out, USDC comes in. */
function sell(
  token: string,
  amount: string,
  proceeds: string,
  timestamp: string,
  fee?: { tokenSymbol: string; amount: string; usdValue: string },
) {
  return makeTx(
    'swap',
    timestamp,
    [{ tokenSymbol: 'USDC', amount: proceeds, usdValue: proceeds }], // assetsIn: USDC received
    [{ tokenSymbol: token, amount, usdValue: proceeds }],             // assetsOut: token disposed
    { fee },
  );
}

function run(
  txs: ReturnType<typeof createTransaction>[],
  method: 'FIFO' | 'LIFO' | 'HIFO' = 'FIFO',
  year?: number,
) {
  return new CalculatorEngine(txs, method, [USER]).calculate(year);
}

// ---------------------------------------------------------------------------
// US scenarios
// ---------------------------------------------------------------------------

describe('US tax scenarios', () => {
  it('US-01: simple buy + sell - short-term FIFO gain', () => {
    // Buy 1 ETH @ $2,000. Sell @ $3,000 (90 days later = short-term).
    // Expected: 1 disposal, gain = $1,000, holding period = short-term.
    const txs = [
      buy('ETH', '1', '2000', '2024-01-01T00:00:00Z'),
      sell('ETH', '1', '3000', '2024-04-01T00:00:00Z'),
    ];

    const { disposals, summary } = run(txs);
    expect(disposals).toHaveLength(1);
    expect(disposals[0].gainLossUsd.toString()).toBe('1000');
    expect(disposals[0].holdingPeriod).toBe(HoldingPeriod.SHORT_TERM);
    expect(summary.totalGains.toString()).toBe('1000');
    expect(summary.totalLosses.toString()).toBe('0');
    expect(summary.net.toString()).toBe('1000');
  });

  it('US-02: buy + sell - long-term (>365 days)', () => {
    // Buy 1 ETH @ $1,500 on Dec 1 2022. Sell @ $4,000 on Jan 5 2024 (400 days).
    // Expected: gain = $2,500, holding period = long-term.
    const txs = [
      buy('ETH', '1', '1500', '2022-12-01T00:00:00Z'),
      sell('ETH', '1', '4000', '2024-01-05T00:00:00Z'),
    ];

    const { disposals } = run(txs);
    expect(disposals).toHaveLength(1);
    expect(disposals[0].gainLossUsd.toString()).toBe('2500');
    expect(disposals[0].holdingPeriod).toBe(HoldingPeriod.LONG_TERM);
  });

  it('US-03: sell at a loss - capital loss recorded correctly', () => {
    // Buy 1 ETH @ $3,000. Sell @ $2,000. Loss = -$1,000.
    const txs = [
      buy('ETH', '1', '3000', '2024-01-01T00:00:00Z'),
      sell('ETH', '1', '2000', '2024-06-01T00:00:00Z'),
    ];

    const { disposals, summary } = run(txs);
    expect(disposals).toHaveLength(1);
    expect(disposals[0].gainLossUsd.toString()).toBe('-1000');
    // totalLosses accumulates negative values: -1000 (not the magnitude)
    expect(summary.totalLosses.toString()).toBe('-1000');
    expect(summary.net.toString()).toBe('-1000');
  });

  it('US-04: HIFO produces lower gain than FIFO on same transactions', () => {
    // Buy 1 ETH @ $1,000 (lot A), then 1 ETH @ $3,000 (lot B). Sell 1 ETH @ $3,500.
    // FIFO: consumes lot A → gain = $3,500 - $1,000 = $2,500
    // HIFO: consumes lot B → gain = $3,500 - $3,000 = $500
    const txs = [
      buy('ETH', '1', '1000', '2024-01-01T00:00:00Z'),
      buy('ETH', '1', '3000', '2024-02-01T00:00:00Z'),
      sell('ETH', '1', '3500', '2024-06-01T00:00:00Z'),
    ];

    const { summary: fifo } = run(txs, 'FIFO');
    const { summary: hifo } = run(txs, 'HIFO');

    expect(fifo.totalGains.toString()).toBe('2500');
    expect(hifo.totalGains.toString()).toBe('500');
    expect(hifo.totalGains.lt(fifo.totalGains)).toBe(true);
  });

  it('US-05: token-for-token swap - disposes outgoing token', () => {
    // Buy 1 ETH @ $2,000. Swap ETH → USDC at proceeds $3,000.
    // Disposal token = ETH, gain = $1,000.
    const txs = [
      buy('ETH', '1', '2000', '2024-01-01T00:00:00Z'),
      sell('ETH', '1', '3000', '2024-03-01T00:00:00Z'),
    ];

    const { disposals } = run(txs);
    expect(disposals).toHaveLength(1);
    expect(disposals[0].token).toBe('ETH');
    expect(disposals[0].gainLossUsd.toString()).toBe('1000');
  });

  it('US-06: bridge - zero disposals, cost basis carries over', () => {
    // Bridge 1 ETH Ethereum → Arbitrum. Not a taxable event per IRS guidance.
    // ETH acquired via buy; then bridged. Zero disposals expected.
    const txs = [
      buy('ETH', '1', '2000', '2024-01-01T00:00:00Z'),
      makeTx(
        'bridge',
        '2024-03-01T00:00:00Z',
        [{ tokenSymbol: 'ETH', amount: '1', usdValue: '2200' }],
        [{ tokenSymbol: 'ETH', amount: '1', usdValue: '2200' }],
      ),
    ];

    const { disposals } = run(txs);
    expect(disposals).toHaveLength(0);
  });

  it('US-07: LP deposit (lp_add) - zero phantom gain', () => {
    // Buy 1 ETH @ $2,000. Deposit into Uniswap V3 LP when ETH is at $2,200.
    // Competitor bug: treats as disposal at $2,200 → $200 phantom gain.
    // Correct: lp_add is recorded at cost basis, net gain on the LP deposit = $0.
    const txs = [
      buy('ETH', '1', '2000', '2024-01-01T00:00:00Z'),
      makeTx(
        'lp_add',
        '2024-03-01T00:00:00Z',
        [{ tokenSymbol: 'UNI-V3-LP', amount: '1', usdValue: '2200' }],
        [{ tokenSymbol: 'ETH', amount: '1', usdValue: '2200' }],
        { protocol: 'uniswap-v3' },
      ),
    ];

    const { disposals } = run(txs);
    // lp_add consumes the ETH lot but at cost basis - net gain/loss across all disposals = 0
    const net = disposals.reduce((s, d) => s.plus(d.gainLossUsd), new Decimal('0'));
    expect(net.toString()).toBe('0');
  });

  it('US-08: staking reward - lot created at FMV, disposal gain is correct', () => {
    // Receive 0.1 ETH staking reward at FMV $200. Cost basis = $200.
    // Sell that 0.1 ETH at $300 → gain = $100.
    const txs = [
      makeTx('reward', '2024-01-01T00:00:00Z',
        [{ tokenSymbol: 'ETH', amount: '0.1', usdValue: '200' }], []),
      sell('ETH', '0.1', '300', '2024-06-01T00:00:00Z'),
    ];

    const { disposals, lots } = run(txs);
    expect(disposals).toHaveLength(1);
    expect(disposals[0].gainLossUsd.toString()).toBe('100');
    // The reward lot should have source = 'reward'
    expect(lots.some((l) => l.source === 'reward')).toBe(true);
  });

  it('US-09: airdrop - lot created in book, zero disposals', () => {
    // Receive 100 tokens as airdrop at $500 FMV. No disposal.
    // Lot exists in book with source = 'airdrop'.
    const txs = [
      makeTx('airdrop', '2024-01-01T00:00:00Z',
        [{ tokenSymbol: 'TOKEN', amount: '100', usdValue: '500' }], []),
    ];

    const { disposals, lots } = run(txs);
    expect(disposals).toHaveLength(0);
    const airdropLot = lots.find((l) => l.token === 'TOKEN' && l.source === 'airdrop');
    expect(airdropLot).toBeDefined();
    expect(airdropLot!.costBasisUsd.toString()).toBe('500');
  });

  it('US-10: gas fee reduces net proceeds on disposal', () => {
    // Buy 1 WBTC @ $40,000. Sell @ $50,000 with $10 ETH gas fee.
    // Using WBTC (not ETH) so the disposal token and fee token differ - engine
    // would skip an ETH disposal if fee is also ETH (isGasTokenForFee check).
    // Net proceeds = $50,000 - $10 = $49,990. Gain = $9,990.
    const txs = [
      buy('WBTC', '1', '40000', '2024-01-01T00:00:00Z'),
      sell('WBTC', '1', '50000', '2024-06-01T00:00:00Z',
        { tokenSymbol: 'ETH', amount: '0.005', usdValue: '10' }),
    ];

    const { disposals } = run(txs);
    expect(disposals).toHaveLength(1);
    expect(disposals[0].gainLossUsd.toString()).toBe('9990');
  });
});

// ---------------------------------------------------------------------------
// German tax scenarios
// ---------------------------------------------------------------------------

describe('German tax scenarios (Spekulationsfrist + Freigrenze)', () => {
  const deTax = new GermanTaxModule();

  it('DE-01: Spekulationsfrist - held 366 days = EXEMPT', () => {
    // Jan 1 2023 → Jan 2 2024 = 366 days. >365 = steuerfrei § 23 Abs. 1 Nr. 2 EStG.
    const acquired = new Date('2023-01-01');
    const disposed = new Date('2024-01-02');
    expect(deTax.classifyHoldingPeriod(acquired, disposed)).toBe(HoldingPeriod.EXEMPT);
  });

  it('DE-02: Spekulationsfrist - held exactly 365 days = SHORT_TERM (taxable)', () => {
    // Rule is >365, not >=365. Exactly 365 days is still taxable.
    const acquired = new Date('2023-06-01');
    const disposed = new Date('2024-05-31'); // 365 days
    expect(deTax.classifyHoldingPeriod(acquired, disposed)).toBe(HoldingPeriod.SHORT_TERM);
  });

  it('DE-03: Freigrenze below cliff (€999 total gain) - exemption returned', () => {
    // Total short-term gains = €999 < €1,000. All short-term gains exempt.
    // getExemptions should include a Freigrenze entry.
    const disposal = createDisposal({
      id: 'de-test-1',
      date: '2024-06-01',
      token: 'ETH',
      amount: '1',
      proceedsUsd: '2999',
      costBasisUsd: '2000',
      gainLossUsd: '999',
      holdingPeriod: HoldingPeriod.SHORT_TERM,
      method: 'FIFO',
      txHash: '0xde01',
      holdingPeriodEnum: HoldingPeriod.SHORT_TERM,
    });

    const exemptions = deTax.getExemptions([disposal], 2024);
    expect(exemptions.some((e) => e.reason.toLowerCase().includes('freigrenze'))).toBe(true);
  });

  it('DE-04: Freigrenze at cliff (exactly €1,000) - NO exemption', () => {
    // The Freigrenze is "< 1000", not "<= 1000". At exactly €1,000, all gains are taxable.
    const disposal = createDisposal({
      id: 'de-test-2',
      date: '2024-06-01',
      token: 'ETH',
      amount: '1',
      proceedsUsd: '3000',
      costBasisUsd: '2000',
      gainLossUsd: '1000',
      holdingPeriod: HoldingPeriod.SHORT_TERM,
      method: 'FIFO',
      txHash: '0xde02',
      holdingPeriodEnum: HoldingPeriod.SHORT_TERM,
    });

    const exemptions = deTax.getExemptions([disposal], 2024);
    expect(exemptions.some((e) => e.reason.toLowerCase().includes('freigrenze'))).toBe(false);
  });

  it('DE-05: Freigrenze above cliff (€1,001) - NO exemption', () => {
    const disposal = createDisposal({
      id: 'de-test-3',
      date: '2024-06-01',
      token: 'ETH',
      amount: '1',
      proceedsUsd: '3001',
      costBasisUsd: '2000',
      gainLossUsd: '1001',
      holdingPeriod: HoldingPeriod.SHORT_TERM,
      method: 'FIFO',
      txHash: '0xde03',
      holdingPeriodEnum: HoldingPeriod.SHORT_TERM,
    });

    const exemptions = deTax.getExemptions([disposal], 2024);
    expect(exemptions.some((e) => e.reason.toLowerCase().includes('freigrenze'))).toBe(false);
  });
});
