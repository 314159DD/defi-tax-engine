"""
Canonical token equivalence mappings.

Wrapped and liquid-staked tokens are economically equivalent to their
underlying asset.  Wrapping/unwrapping is generally NOT a taxable event.
Rebasing tokens (e.g. stETH) generate daily income events from balance
changes and are flagged separately.

Usage:
    from src.data.token_pairs import is_equivalent, is_rebasing_token
"""
from __future__ import annotations


# ── Wrapped / staked → canonical underlying ─────────────────────────────────
# Keys are UPPERCASE symbols.  Values are the canonical "base" symbol.
EQUIVALENT_TOKENS: dict[str, str] = {
    # Wrapped ETH variants
    "WETH":    "ETH",
    "STETH":   "ETH",
    "WSTETH":  "ETH",
    "CBETH":   "ETH",
    "RETH":    "ETH",
    "FRXETH":  "ETH",
    "SFRXETH": "ETH",
    "METH":    "ETH",     # Mantle staked ETH
    "OETH":    "ETH",     # Origin ETH
    "ANKRETH": "ETH",     # Ankr staked ETH
    "SWETH":   "ETH",     # Swell ETH
    "SETH2":   "ETH",     # StakeWise staked ETH
    # Wrapped BTC variants
    "WBTC":    "BTC",
    "TBTC":    "BTC",
    "RENBTC":  "BTC",
    "SBTC":    "BTC",
    "HBTC":    "BTC",
    "CBTC":    "BTC",
    # Wrapped MATIC / POL
    "WMATIC":  "MATIC",
    "STMATIC": "MATIC",
    "MATICX":  "MATIC",
    # Wrapped BNB
    "WBNB":    "BNB",
    "SBNB":    "BNB",
    # Wrapped SOL
    "WSOL":    "SOL",
    "MSOL":    "SOL",
    "STSOL":   "SOL",
    "JITOSOL": "SOL",
    "BSOL":    "SOL",
    # Wrapped AVAX
    "WAVAX":   "AVAX",
    "SAVAX":   "AVAX",
    # Stablecoins - canonical bridges
    "USDC.E":  "USDC",
    "USDCE":   "USDC",
    "USDT.E":  "USDT",
    "DAI.E":   "DAI",
    "USDbC":   "USDC",    # Base bridged USDC
}

# ── Rebasing tokens (balance changes daily = income event) ──────────────────
REBASING_TOKENS: frozenset[str] = frozenset({
    "STETH",
    "AETHUSDC",  # Aave aToken
    "AETHUSDT",
    "AETHDAI",
    "AETHWETH",
    "AUSDC",     # Aave V2 aTokens
    "AUSDT",
    "ADAI",
    "AWETH",
    "ASTETH",
})


def canonical_symbol(symbol: str) -> str:
    """
    Return the canonical base symbol for a token.

    If the token is in the equivalence map, returns the underlying asset.
    Otherwise returns the symbol as-is (uppercased).

    Examples:
        canonical_symbol("WETH")  -> "ETH"
        canonical_symbol("USDC")  -> "USDC"
        canonical_symbol("stETH") -> "ETH"
    """
    return EQUIVALENT_TOKENS.get(symbol.upper(), symbol.upper())


def is_equivalent(token_a: str, token_b: str) -> bool:
    """
    Return True if two tokens are economically equivalent.

    Checks whether both tokens map to the same canonical symbol.
    For example, WETH and stETH are both equivalent to ETH.

    Args:
        token_a: First token symbol (case-insensitive).
        token_b: Second token symbol (case-insensitive).
    """
    return canonical_symbol(token_a) == canonical_symbol(token_b)


def is_rebasing_token(token: str) -> bool:
    """
    Return True if the token rebases (balance changes generate income).

    Rebasing tokens like stETH increase in balance daily.  Each balance
    increase is an income event at FMV on that day.

    Args:
        token: Token symbol (case-insensitive).
    """
    return token.upper() in REBASING_TOKENS
