/**
 * Re-exports all categorization rules.
 *
 * Each rule exports an `apply(tx, context)` function that returns
 * an updated Transaction if the rule matches, or null if it doesn't.
 */

export * as swap from './swap';
export * as bridge from './bridge';
export * as transfer from './transfer';
export * as staking from './staking';
export * as liquidity from './liquidity';
export * as lending from './lending';
export * as vault from './vault';
export * as uniswapV3 from './uniswap-v3';
export * as nft from './nft';
export * as airdrop from './airdrop';
