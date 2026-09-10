/**
 * Lending protocol deposit/withdrawal/liquidation detection.
 *
 * Supported protocols:
 * - Aave V2/V3 (aToken / Pool contract)
 * - Compound V2 (cToken / Comptroller)
 * - Compound V3 (Comet contracts)
 *
 * Ported from: src/categorizer/rules/lending.py
 */

import type { AssetTransfer, Transaction } from '../../types';
import {
  AAVE_V2_POOL,
  AAVE_V3_POOL,
  COMPOUND_V2_COMPTROLLER,
  COMPOUND_V3_USDC,
  resolveProtocol,
} from '../protocols';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

// -- Contract address sets --
const AAVE_POOL_ADDRESSES: ReadonlySet<string> = new Set([AAVE_V2_POOL, AAVE_V3_POOL]);

const COMPOUND_ADDRESSES: ReadonlySet<string> = new Set([
  COMPOUND_V2_COMPTROLLER,
  COMPOUND_V3_USDC,
]);

const LENDING_ADDRESSES: ReadonlySet<string> = new Set([
  ...Array.from(AAVE_POOL_ADDRESSES),
  ...Array.from(COMPOUND_ADDRESSES),
]);

// -- aToken / cToken detection --
const ATOKEN_RE = /^a[A-Z]/i; // aUSDC, aWETH, aDAI
const ATOKEN_V3_RE = /^aEth[A-Z]/i; // aEthUSDC (Aave V3 on ETH)
const CTOKEN_RE = /^c[A-Z]/i; // cUSDC, cETH, cDAI

const LENDING_TOKEN_PATTERNS = [ATOKEN_RE, ATOKEN_V3_RE, CTOKEN_RE];

function isLendingReceiptToken(transfer: AssetTransfer): boolean {
  const sym = transfer.tokenSymbol;
  return LENDING_TOKEN_PATTERNS.some((p) => p.test(sym));
}

function toLendingContract(tx: Transaction): boolean {
  return LENDING_ADDRESSES.has(tx.toAddress.toLowerCase());
}

function fromLendingContract(tx: Transaction): boolean {
  return LENDING_ADDRESSES.has(tx.fromAddress.toLowerCase());
}

function protocolIsLending(tx: Transaction): boolean {
  if (!tx.protocol) return false;
  const lower = tx.protocol.toLowerCase();
  return ['aave', 'compound', 'lending', 'morpho', 'spark'].some((kw) => lower.includes(kw));
}

/**
 * Detect lending deposit: user sends underlying, receives aToken/cToken.
 */
export function isLendingDeposit(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;

  const hasReceiptIn = tx.assetsIn.some(isLendingReceiptToken);
  const hasReceiptOut = tx.assetsOut.some(isLendingReceiptToken);

  // Deposit: send underlying, receive aToken/cToken
  if (hasReceiptIn && !hasReceiptOut) {
    if (toLendingContract(tx) || protocolIsLending(tx)) return true;
  }

  return false;
}

/**
 * Detect lending withdrawal: user burns aToken/cToken, receives underlying.
 */
export function isLendingWithdraw(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;

  const hasReceiptIn = tx.assetsIn.some(isLendingReceiptToken);
  const hasReceiptOut = tx.assetsOut.some(isLendingReceiptToken);

  // Withdraw: send aToken/cToken, receive underlying
  if (hasReceiptOut && !hasReceiptIn) {
    if (toLendingContract(tx) || fromLendingContract(tx) || protocolIsLending(tx)) return true;
  }

  return false;
}

/**
 * Detect liquidation: forced closure of under-collateralized position.
 */
export function isLendingLiquidation(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0) return false;

  const method =
    (tx.rawData.method as string) ?? (tx.rawData.functionName as string) ?? '';
  if (typeof method === 'string' && method.toLowerCase().includes('liquidat')) {
    if (toLendingContract(tx) || fromLendingContract(tx) || protocolIsLending(tx)) {
      return true;
    }
  }

  return false;
}

/**
 * Classify as 'lending_deposit', 'lending_withdraw', or 'lending_liquidation'.
 * Returns null if the rule does not apply.
 */
export function apply(tx: Transaction, _context: CategorizerContext): Transaction | null {
  const protocol = tx.protocol || resolveProtocol(tx.toAddress);

  if (isLendingLiquidation(tx)) {
    return { ...tx, txType: 'lending_liquidation', protocol: protocol || 'Lending' };
  }

  if (isLendingDeposit(tx)) {
    return { ...tx, txType: 'lending_deposit', protocol: protocol || 'Lending' };
  }

  if (isLendingWithdraw(tx)) {
    return { ...tx, txType: 'lending_withdraw', protocol: protocol || 'Lending' };
  }

  return null;
}
