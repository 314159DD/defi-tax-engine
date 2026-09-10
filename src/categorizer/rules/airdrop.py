"""
Airdrop detection rule.

An airdrop is tokens received with no corresponding outgoing assets.
It IS income - taxed as ordinary income at FMV on the date of receipt.
The cost basis of airdropped tokens = FMV at receipt date.

Also handles token distributions: governance rewards, protocol incentives, etc.
"""
from __future__ import annotations

from src.categorizer.protocols import STAKING_ADDRESSES
from src.importers.models import Transaction


def is_airdrop(tx: Transaction, known_wallets: set[str]) -> bool:
    """
    Return True if this transaction looks like an airdrop.

    Conditions:
    1. Assets received (assets_in non-empty)
    2. No assets sent (assets_out empty)
    3. NOT from a staking contract (handled by staking rule)
    4. Sender is NOT a user wallet (not a self-transfer)
    5. NOT a bridge receive (handled by bridge rule - assets_in on the destination
       chain with matching bridge from_address are bridges; we rely on ordering)
    """
    if not tx.assets_in:
        return False
    if tx.assets_out:
        return False

    lower_wallets = {w.lower() for w in known_wallets}

    # If sender is a user wallet, this is a self-transfer not an airdrop
    if tx.from_address.lower() in lower_wallets:
        return False

    # If sent from a staking contract, let staking rule handle it
    if tx.from_address.lower() in STAKING_ADDRESSES:
        return False

    # Transaction must have minimal or no contract call (pure token distribution)
    # Receiving tokens with no matching send = airdrop
    return True


def apply(tx: Transaction, known_wallets: set[str]) -> Transaction | None:
    """
    If this is an airdrop, set tx_type to 'airdrop' and return updated tx.
    Returns None if rule does not apply.
    """
    if not is_airdrop(tx, known_wallets):
        return None

    return Transaction(
        tx_hash=tx.tx_hash,
        chain=tx.chain,
        block_number=tx.block_number,
        timestamp=tx.timestamp,
        from_address=tx.from_address,
        to_address=tx.to_address,
        tx_type="airdrop",
        assets_in=tx.assets_in,
        assets_out=tx.assets_out,
        fee=tx.fee,
        protocol=tx.protocol,
        raw_data=tx.raw_data,
    )
