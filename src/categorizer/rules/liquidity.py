"""
LP (liquidity position) add/remove detection rule.

LP add: user sends two tokens to an AMM pool and receives LP tokens.
LP remove: user burns LP tokens and receives two tokens back.

Tax treatment:
- LP add: NOT immediately taxable. Cost basis of LP token = sum of deposited tokens FMV.
- LP remove: IS a taxable event. Dispose of LP token at FMV of received tokens.
  Impermanent loss is only realized at LP removal.
"""
from __future__ import annotations

import re

from src.categorizer.protocols import DEX_ADDRESSES, resolve_protocol
from src.importers.models import AssetTransfer, Transaction

# LP token symbol patterns
_LP_SYMBOL_RE = re.compile(
    r"(?i)(UNI-V[23]|SLP|CAKE-LP|SUSHI|crv|BPT|LP|POOL|[A-Z]+-[A-Z]+\s*LP)",
    re.IGNORECASE,
)

# Common LP token name keywords
_LP_KEYWORDS = ("uni-v", "slp", "cake-lp", "-lp", "lp-", "lpt", "pool", "bpt", "crv")


def _is_lp_token(transfer: AssetTransfer) -> bool:
    """Heuristic: is this transfer an LP token?"""
    sym = transfer.token_symbol.lower()
    if any(kw in sym for kw in _LP_KEYWORDS):
        return True
    if _LP_SYMBOL_RE.search(transfer.token_symbol):
        return True
    return False


def is_lp_add(tx: Transaction) -> bool:
    """
    Detect LP add: user sends 1-2 tokens and receives LP token.

    Patterns:
    1. assets_out has 1-2 non-LP tokens, assets_in has an LP token
    2. to_address is a known DEX
    """
    if not tx.assets_in or not tx.assets_out:
        return False

    has_lp_in = any(_is_lp_token(t) for t in tx.assets_in)
    has_lp_out = any(_is_lp_token(t) for t in tx.assets_out)

    # Classic: send tokens, receive LP token
    if has_lp_in and not has_lp_out:
        to_addr = tx.to_address.lower()
        if to_addr in DEX_ADDRESSES:
            return True
        # Also match if protocol is a known DEX
        if tx.protocol and any(
            kw in tx.protocol.lower()
            for kw in ("uniswap", "sushiswap", "curve", "balancer", "pancakeswap",
                       "quickswap", "raydium", "orca")
        ):
            return True

    return False


def is_lp_remove(tx: Transaction) -> bool:
    """
    Detect LP remove: user burns LP token and receives underlying tokens.

    Patterns:
    1. assets_out has LP token, assets_in has 1-2 non-LP tokens
    """
    if not tx.assets_in or not tx.assets_out:
        return False

    has_lp_out = any(_is_lp_token(t) for t in tx.assets_out)
    has_lp_in = any(_is_lp_token(t) for t in tx.assets_in)

    if has_lp_out and not has_lp_in:
        to_addr = tx.to_address.lower()
        if to_addr in DEX_ADDRESSES:
            return True
        if tx.protocol and any(
            kw in tx.protocol.lower()
            for kw in ("uniswap", "sushiswap", "curve", "balancer", "pancakeswap",
                       "quickswap", "raydium", "orca")
        ):
            return True

    return False


def apply(tx: Transaction) -> Transaction | None:
    """
    Classify as 'lp_add' or 'lp_remove' if applicable.
    Returns None if rule does not apply.
    """
    protocol = tx.protocol or resolve_protocol(tx.to_address)

    if is_lp_add(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="lp_add",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "AMM",
            raw_data=tx.raw_data,
        )

    if is_lp_remove(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="lp_remove",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "AMM",
            raw_data=tx.raw_data,
        )

    return None
