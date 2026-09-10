"""
Transaction data models for crypto tax calculations.
CRITICAL: All monetary values use decimal.Decimal - NEVER float.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class AssetTransfer:
    """Represents a single asset movement within a transaction."""
    token_symbol: str
    amount: Decimal                  # DECIMAL, never float
    token_address: Optional[str] = None   # None for native assets (ETH, SOL, MATIC)
    usd_value: Optional[Decimal] = None   # USD value at time of tx


@dataclass
class Transaction:
    """
    Normalized transaction model across all chains.

    tx_type values:
      transfer, swap, lp_add, lp_remove, stake, unstake, reward,
      bridge, airdrop, mint, burn, approve, unknown
    """
    tx_hash: str
    chain: str                          # ethereum, polygon, arbitrum, base, optimism, solana
    block_number: int
    timestamp: datetime
    from_address: str
    to_address: str
    tx_type: str                        # see docstring above
    assets_in: list[AssetTransfer]      # What the wallet received
    assets_out: list[AssetTransfer]     # What the wallet sent
    fee: Optional[AssetTransfer]        # Gas / transaction fee
    protocol: Optional[str]             # Uniswap, Aave, Lido, etc.
    raw_data: dict = field(default_factory=dict)  # Original API response

    def __post_init__(self) -> None:
        # Enforce Decimal on any numeric fields passed accidentally as float
        for transfer in [*self.assets_in, *self.assets_out]:
            if not isinstance(transfer.amount, Decimal):
                raise TypeError(
                    f"AssetTransfer.amount must be Decimal, got {type(transfer.amount)} "
                    f"for {transfer.token_symbol}"
                )
        if self.fee and not isinstance(self.fee.amount, Decimal):
            raise TypeError(
                f"Fee amount must be Decimal, got {type(self.fee.amount)}"
            )
