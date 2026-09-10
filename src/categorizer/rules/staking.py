"""
Staking transaction detection rules.

Stake:   user sends tokens to staking contract. NOT immediately taxable.
         Cost basis of staked position = original token cost basis.
Unstake: user receives tokens back from staking. NOT taxable if same token.
Reward:  user receives staking reward tokens. IS income (ordinary).
         Cost basis of reward = FMV at time of receipt.
"""
from __future__ import annotations

from src.categorizer.protocols import STAKING_ADDRESSES, resolve_protocol
from src.importers.models import Transaction

# Known staking reward token symbols
_REWARD_SYMBOLS = frozenset({
    "LDO", "RPL", "CVX", "CRV", "AAVE", "COMP", "MKR",
    "SNX", "FXS", "ANKR", "RETH", "STETH", "WSTETH",
    "CBETH", "FRXETH", "SFRXETH",
})

# Known liquid staking deposit symbols (stake ETH → get stToken)
_LIQUID_STAKE_IN_SYMBOLS = frozenset({"ETH", "WETH", "MATIC", "BNB", "SOL"})
_LIQUID_STAKE_OUT_SYMBOLS = frozenset({
    "STETH", "WSTETH", "RETH", "CBETH", "FRXETH", "SFRXETH",
    "STMATIC", "BMATIC", "MSOL", "STSOL", "JITOSOL",
})


def _to_staking_contract(tx: Transaction) -> bool:
    """True if to_address is a known staking contract."""
    return tx.to_address.lower() in STAKING_ADDRESSES


def _protocol_is_staking(tx: Transaction) -> bool:
    if not tx.protocol:
        return False
    lower = tx.protocol.lower()
    return any(kw in lower for kw in ("lido", "rocket", "rocketpool", "frax", "convex",
                                       "yearn", "beefy", "stake", "staking"))


def is_stake(tx: Transaction) -> bool:
    """User deposits tokens into staking contract (no reward yet)."""
    if not tx.assets_out:
        return False
    if not (_to_staking_contract(tx) or _protocol_is_staking(tx)):
        return False

    # Sending tokens, receiving either nothing or a liquid staking token
    out_symbols = {t.token_symbol.upper() for t in tx.assets_out}
    in_symbols  = {t.token_symbol.upper() for t in tx.assets_in}

    # Liquid staking: send ETH, get stETH/rETH etc.
    if out_symbols & _LIQUID_STAKE_IN_SYMBOLS and in_symbols & _LIQUID_STAKE_OUT_SYMBOLS:
        return True

    # Plain stake: send tokens, receive nothing (or a position token)
    if tx.assets_out and not tx.assets_in:
        return True

    return False


def is_unstake(tx: Transaction) -> bool:
    """User withdraws staked tokens (not reward collection)."""
    if not tx.assets_in:
        return False
    if not (_to_staking_contract(tx) or _protocol_is_staking(tx)):
        return False

    out_symbols = {t.token_symbol.upper() for t in tx.assets_out}
    in_symbols  = {t.token_symbol.upper() for t in tx.assets_in}

    # Liquid unstake: send stETH/rETH, get ETH back
    if out_symbols & _LIQUID_STAKE_OUT_SYMBOLS and in_symbols & _LIQUID_STAKE_IN_SYMBOLS:
        return True

    # Plain unstake: receive tokens, send nothing
    if tx.assets_in and not tx.assets_out:
        return True

    return False


def is_staking_reward(tx: Transaction) -> bool:
    """
    User claims staking rewards.

    Indicators:
    1. Receives tokens from a staking contract with no corresponding send
    2. Token symbol is a known reward token
    3. No assets_out (pure claim)
    """
    if not tx.assets_in or tx.assets_out:
        return False

    if _to_staking_contract(tx) or _protocol_is_staking(tx):
        return True

    # Fallback: any incoming transfer of known reward tokens with no outgoing
    in_symbols = {t.token_symbol.upper() for t in tx.assets_in}
    if in_symbols & _REWARD_SYMBOLS:
        return True

    return False


def apply(tx: Transaction) -> Transaction | None:
    """
    Classify as 'stake', 'unstake', or 'reward' if applicable.
    Returns None if rule does not apply.
    """
    protocol = tx.protocol or resolve_protocol(tx.to_address)

    if is_staking_reward(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="reward",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "Staking",
            raw_data=tx.raw_data,
        )

    if is_stake(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="stake",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "Staking",
            raw_data=tx.raw_data,
        )

    if is_unstake(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="unstake",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "Staking",
            raw_data=tx.raw_data,
        )

    return None
