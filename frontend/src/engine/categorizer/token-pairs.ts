/**
 * Canonical token equivalence mappings.
 *
 * Wrapped and liquid-staked tokens are economically equivalent to their
 * underlying asset. Wrapping/unwrapping is generally NOT a taxable event.
 * Rebasing tokens (e.g. stETH) generate daily income events from balance
 * changes and are flagged separately.
 *
 * Ported from: src/data/token_pairs.py
 */

// -- Wrapped / staked -> canonical underlying --
// Keys are UPPERCASE symbols. Values are the canonical "base" symbol.
export const EQUIVALENT_TOKENS: Record<string, string> = {
  // Wrapped ETH variants
  WETH: 'ETH',
  STETH: 'ETH',
  WSTETH: 'ETH',
  CBETH: 'ETH',
  RETH: 'ETH',
  FRXETH: 'ETH',
  SFRXETH: 'ETH',
  METH: 'ETH', // Mantle staked ETH
  OETH: 'ETH', // Origin ETH
  ANKRETH: 'ETH', // Ankr staked ETH
  SWETH: 'ETH', // Swell ETH
  SETH2: 'ETH', // StakeWise staked ETH
  // Wrapped BTC variants
  WBTC: 'BTC',
  TBTC: 'BTC',
  RENBTC: 'BTC',
  SBTC: 'BTC',
  HBTC: 'BTC',
  CBTC: 'BTC',
  // Wrapped MATIC / POL
  WMATIC: 'MATIC',
  STMATIC: 'MATIC',
  MATICX: 'MATIC',
  // Wrapped BNB
  WBNB: 'BNB',
  SBNB: 'BNB',
  // Wrapped SOL
  WSOL: 'SOL',
  MSOL: 'SOL',
  STSOL: 'SOL',
  JITOSOL: 'SOL',
  BSOL: 'SOL',
  // Wrapped AVAX
  WAVAX: 'AVAX',
  SAVAX: 'AVAX',
  // Stablecoins -- canonical bridges
  'USDC.E': 'USDC',
  USDCE: 'USDC',
  'USDT.E': 'USDT',
  'DAI.E': 'DAI',
  USDbC: 'USDC', // Base bridged USDC
};

// -- Rebasing tokens (balance changes daily = income event) --
export const REBASING_TOKENS: ReadonlySet<string> = new Set([
  'STETH',
  'AETHUSDC', // Aave aToken
  'AETHUSDT',
  'AETHDAI',
  'AETHWETH',
  'AUSDC', // Aave V2 aTokens
  'AUSDT',
  'ADAI',
  'AWETH',
  'ASTETH',
]);

/**
 * Return the canonical base symbol for a token.
 *
 * If the token is in the equivalence map, returns the underlying asset.
 * Otherwise returns the symbol as-is (uppercased).
 *
 * Examples:
 *   canonicalSymbol("WETH")  -> "ETH"
 *   canonicalSymbol("USDC")  -> "USDC"
 *   canonicalSymbol("stETH") -> "ETH"
 */
export function canonicalSymbol(symbol: string): string {
  const upper = symbol.toUpperCase();
  return EQUIVALENT_TOKENS[upper] ?? upper;
}

/**
 * Return true if two tokens are economically equivalent.
 *
 * Checks whether both tokens map to the same canonical symbol.
 * For example, WETH and stETH are both equivalent to ETH.
 */
export function isEquivalent(tokenA: string, tokenB: string): boolean {
  return canonicalSymbol(tokenA) === canonicalSymbol(tokenB);
}

/**
 * Return true if the token rebases (balance changes generate income).
 *
 * Rebasing tokens like stETH increase in balance daily. Each balance
 * increase is an income event at FMV on that day.
 */
export function isRebasingToken(token: string): boolean {
  return REBASING_TOKENS.has(token.toUpperCase());
}
