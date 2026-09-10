/**
 * Auto-compounding vault deposit/withdrawal detection.
 *
 * Vaults accept underlying tokens and return vault shares (yvDAI, mooXYZ, etc.).
 *
 * Supported protocols:
 * - Yearn V2/V3 (yvToken pattern)
 * - Beefy (mooToken pattern)
 * - Convex (cvxToken pattern)
 *
 * Ported from: src/categorizer/rules/vault.py
 */

import type { AssetTransfer, Transaction } from '../../types';
import { resolveProtocol } from '../protocols';

export interface CategorizerContext {
  knownWallets: ReadonlySet<string>;
}

// -- Known vault contract addresses --
const VAULT_ADDRESSES: ReadonlySet<string> = new Set([
  // Yearn V2 vaults (representative set)
  '0x19d3364a399d251e894ac732651be8b0e4e85001', // yvDAI
  '0xa354f35829ae975e850e23e9615b11da1b3dc4de', // yvUSDC
  '0xa258c4606ca8206d8aa700ce2143d7db854d168c', // yvWETH
  '0x7da96a3891add058ada2e826306d812c638d87a7', // yvUSDT
  // Yearn V3
  '0x028edc7d75a4f7e30755a3634e1c3cfbd6a9e101', // Yearn V3 example
  // Beefy vaults (representative set)
  '0x453d4ba9a2d594314df88564248497f7d74d6b2c', // moo example
  // Convex
  '0xf403c135812408bfbe8713b5a23a04b3d48aae31', // Convex Booster
  '0x4e3fbd56cd56c3e72c1403e103b45db9da5b9d2b', // CVX token
]);

// -- Vault share token patterns --
const YEARN_RE = /^yv[A-Z]/i; // yvDAI, yvUSDC, yvWETH
const BEEFY_RE = /^moo[A-Z]/i; // mooCurveDAI, mooAaveETH
const CONVEX_RE = /^cvx[A-Z]/i; // cvxCRV, cvxFXS
const YEARN_V3_RE = /^ys?[A-Z]/i; // yDAI, ysDAI (V3 naming)

const VAULT_PATTERNS = [YEARN_RE, BEEFY_RE, CONVEX_RE, YEARN_V3_RE];

function isVaultToken(transfer: AssetTransfer): boolean {
  const sym = transfer.tokenSymbol;
  return VAULT_PATTERNS.some((p) => p.test(sym));
}

function toVaultContract(tx: Transaction): boolean {
  return VAULT_ADDRESSES.has(tx.toAddress.toLowerCase());
}

function protocolIsVault(tx: Transaction): boolean {
  if (!tx.protocol) return false;
  const lower = tx.protocol.toLowerCase();
  return ['yearn', 'beefy', 'convex', 'vault'].some((kw) => lower.includes(kw));
}

/**
 * Detect vault deposit: user sends underlying token, receives vault shares.
 */
export function isVaultDeposit(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;

  const hasVaultIn = tx.assetsIn.some(isVaultToken);
  const hasVaultOut = tx.assetsOut.some(isVaultToken);

  // Deposit: send underlying, receive vault share
  if (hasVaultIn && !hasVaultOut) {
    if (toVaultContract(tx) || protocolIsVault(tx)) return true;
  }

  return false;
}

/**
 * Detect vault withdrawal: user burns vault shares, receives underlying tokens.
 */
export function isVaultWithdraw(tx: Transaction): boolean {
  if (tx.assetsIn.length === 0 || tx.assetsOut.length === 0) return false;

  const hasVaultIn = tx.assetsIn.some(isVaultToken);
  const hasVaultOut = tx.assetsOut.some(isVaultToken);

  // Withdraw: send vault share, receive underlying
  if (hasVaultOut && !hasVaultIn) {
    if (toVaultContract(tx) || protocolIsVault(tx)) return true;
  }

  return false;
}

/**
 * Classify as 'vault_deposit' or 'vault_withdraw' if applicable.
 * Returns null if the rule does not apply.
 */
export function apply(tx: Transaction, _context: CategorizerContext): Transaction | null {
  const protocol = tx.protocol || resolveProtocol(tx.toAddress);

  if (isVaultDeposit(tx)) {
    return { ...tx, txType: 'vault_deposit', protocol: protocol || 'Vault' };
  }

  if (isVaultWithdraw(tx)) {
    return { ...tx, txType: 'vault_withdraw', protocol: protocol || 'Vault' };
  }

  return null;
}
