"""
Self-transfer detection rule.

A self-transfer is a transaction where both the from and to addresses belong
to the user's known wallets. It is NOT a taxable event - the cost basis
carries over to the destination wallet.
"""
from __future__ import annotations

from src.importers.models import Transaction


def is_self_transfer(tx: Transaction, known_wallets: set[str]) -> bool:
    """
    Return True if this transaction is a self-transfer between user wallets.

    Args:
        tx: The normalized transaction.
        known_wallets: Lowercase set of all wallet addresses owned by the user.
    """
    lower_wallets = {w.lower() for w in known_wallets}
    return (
        tx.from_address.lower() in lower_wallets
        and tx.to_address.lower() in lower_wallets
    )


def apply(tx: Transaction, known_wallets: set[str]) -> Transaction | None:
    """
    If this is a self-transfer, set tx_type to 'transfer' and return updated tx.
    Returns None if rule does not apply.
    """
    if is_self_transfer(tx, known_wallets):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="transfer",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=tx.protocol,
            raw_data=tx.raw_data,
        )
    return None
