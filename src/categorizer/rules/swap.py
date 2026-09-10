"""
DEX swap detection rule.

A swap exchanges token A for token B via a DEX. It IS a taxable event:
- The tokens sent out are a disposal (potential capital gain/loss)
- The tokens received set the acquisition cost basis
"""
from __future__ import annotations

from src.categorizer.protocols import DEX_ADDRESSES, resolve_protocol
from src.importers.models import Transaction


# Known wrapped token symbol pairs - wrapping is NOT taxable
_WRAP_SYMBOL_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("ETH", "WETH"),
    ("WETH", "ETH"),
    ("BTC", "WBTC"),
    ("WBTC", "BTC"),
    ("MATIC", "WMATIC"),
    ("WMATIC", "MATIC"),
    ("BNB", "WBNB"),
    ("WBNB", "BNB"),
})


def _is_wrap(tx: Transaction) -> bool:
    """Return True if assets_in/out match a known wrap pair (not taxable)."""
    if len(tx.assets_in) == 1 and len(tx.assets_out) == 1:
        pair = (tx.assets_out[0].token_symbol.upper(), tx.assets_in[0].token_symbol.upper())
        return pair in _WRAP_SYMBOL_PAIRS
    return False


def is_swap(tx: Transaction) -> bool:
    """
    Return True if this transaction is a DEX swap.

    Conditions:
    - Has both assets_in and assets_out
    - to_address is a known DEX router, OR protocol is a known DEX
    - NOT a wrap (ETH→WETH etc.)
    """
    if not tx.assets_in or not tx.assets_out:
        return False

    to_addr = tx.to_address.lower()
    if to_addr in DEX_ADDRESSES:
        return not _is_wrap(tx)

    # Protocol already resolved (e.g. from Solana parser)
    if tx.protocol and any(
        kw in tx.protocol.lower()
        for kw in ("uniswap", "sushiswap", "curve", "balancer", "1inch", "paraswap",
                   "pancakeswap", "quickswap", "trader joe", "raydium", "orca", "jupiter")
    ):
        return not _is_wrap(tx)

    return False


def apply(tx: Transaction) -> Transaction | None:
    """
    If this is a DEX swap, set tx_type to 'swap' and return updated tx.
    Returns None if rule does not apply.
    """
    if not is_swap(tx):
        return None

    protocol = tx.protocol or resolve_protocol(tx.to_address) or "DEX"
    return Transaction(
        tx_hash=tx.tx_hash,
        chain=tx.chain,
        block_number=tx.block_number,
        timestamp=tx.timestamp,
        from_address=tx.from_address,
        to_address=tx.to_address,
        tx_type="swap",
        assets_in=tx.assets_in,
        assets_out=tx.assets_out,
        fee=tx.fee,
        protocol=protocol,
        raw_data=tx.raw_data,
    )
