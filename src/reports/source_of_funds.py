"""
Source of Funds report generator - transaction trail for KYC compliance.

German and Austrian banks increasingly require "Herkunftsnachweis" (proof of
origin) for crypto→fiat conversions.  This module traces each current holding
backward through the full transaction history to produce a chain-of-custody
report.

CRITICAL: All monetary values use decimal.Decimal - NEVER float.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from src.storage.database import (
    Database,
    TaxLotRepository,
    TransactionRepository,
    WalletRepository,
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FundingStep:
    """One step in the chain of custody."""
    step_number: int
    date: date
    action: str  # "purchased", "received_staking_reward", "swapped", "bridged", "transferred", "airdrop"
    source: str  # "Coinbase", "Uniswap V3", "Lido Staking", "Bridge from Ethereum"
    token: str
    amount: Decimal
    value_usd: Decimal  # FMV at time of action
    tx_hash: Optional[str]
    chain: str

    def as_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "date": self.date.isoformat(),
            "action": self.action,
            "source": self.source,
            "token": self.token,
            "amount": str(self.amount),
            "value_usd": str(self.value_usd),
            "tx_hash": self.tx_hash,
            "chain": self.chain,
        }


@dataclass
class HoldingOrigin:
    """Complete origin trace for a single holding."""
    token: str
    current_amount: Decimal
    current_value_usd: Decimal
    wallet_address: str
    chain: str
    acquisition_method: str  # "exchange_purchase", "staking_reward", "defi_yield", "airdrop", "swap", "transfer"
    original_acquisition_date: date
    original_acquisition_cost: Decimal
    funding_trail: list[FundingStep] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "token": self.token,
            "current_amount": str(self.current_amount),
            "current_value_usd": str(self.current_value_usd),
            "wallet_address": self.wallet_address,
            "chain": self.chain,
            "acquisition_method": self.acquisition_method,
            "original_acquisition_date": self.original_acquisition_date.isoformat(),
            "original_acquisition_cost": str(self.original_acquisition_cost),
            "funding_trail": [s.as_dict() for s in self.funding_trail],
        }


@dataclass
class SourceOfFundsReport:
    """Top-level report wrapping all holding origins."""
    generated_at: datetime
    wallet_addresses: list[str]
    holdings: list[HoldingOrigin]
    total_portfolio_value: Decimal
    total_acquisition_cost: Decimal

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "wallet_addresses": self.wallet_addresses,
            "holdings": [h.as_dict() for h in self.holdings],
            "total_portfolio_value": str(self.total_portfolio_value),
            "total_acquisition_cost": str(self.total_acquisition_cost),
        }


# ---------------------------------------------------------------------------
# Source classification
# ---------------------------------------------------------------------------

# Map tax_lot source field → user-facing acquisition method
_SOURCE_TO_METHOD: dict[str, str] = {
    "swap": "swap",
    "reward": "staking_reward",
    "airdrop": "airdrop",
    "mining": "mining",
    "validator": "staking_reward",
    "interest": "defi_yield",
    "lp_add": "defi_yield",
    "lp_remove": "defi_yield",
    "nft_buy": "exchange_purchase",
    "wrap": "swap",
    "bridge": "transfer",
    "transfer": "transfer",
}

# Map tax_lot source → FundingStep action verb
_SOURCE_TO_ACTION: dict[str, str] = {
    "swap": "swapped",
    "reward": "received_staking_reward",
    "airdrop": "airdrop",
    "mining": "received_mining_reward",
    "validator": "received_staking_reward",
    "interest": "received_defi_yield",
    "lp_add": "provided_liquidity",
    "lp_remove": "removed_liquidity",
    "nft_buy": "purchased",
    "wrap": "swapped",
    "bridge": "bridged",
    "transfer": "transferred",
}


def _classify_acquisition_method(source: str) -> str:
    """Map the tax lot source to a user-facing acquisition method."""
    return _SOURCE_TO_METHOD.get(source, "exchange_purchase")


def _classify_action(source: str) -> str:
    """Map the tax lot source to a FundingStep action verb."""
    return _SOURCE_TO_ACTION.get(source, "purchased")


def _extract_chain_from_tx(tx_data: dict) -> str:
    """Extract chain from a transaction row dict."""
    return tx_data.get("chain", "unknown")


def _extract_protocol(tx_data: dict) -> str:
    """Extract a human-readable protocol/source from a transaction."""
    protocol = tx_data.get("protocol")
    if protocol:
        return protocol

    tx_type = tx_data.get("tx_type", "")
    raw = tx_data.get("raw_data")
    if isinstance(raw, dict):
        # Try to extract from_address label or protocol from raw
        protocol = raw.get("protocol")
        if protocol:
            return protocol

    # Fallback based on type
    type_labels = {
        "swap": "DEX Swap",
        "reward": "Staking Protocol",
        "airdrop": "Airdrop",
        "bridge": "Cross-chain Bridge",
        "transfer": "Wallet Transfer",
    }
    return type_labels.get(tx_type, "Unknown")


def _parse_date(date_str: str | None) -> date:
    """Parse ISO date/datetime string to a date object."""
    if not date_str:
        return date.today()
    try:
        return datetime.fromisoformat(date_str).date()
    except (ValueError, TypeError):
        return date.today()


# ---------------------------------------------------------------------------
# Trail builder
# ---------------------------------------------------------------------------

def _build_trail_for_lot(
    lot: dict,
    transactions: list[dict],
    known_addresses: set[str],
) -> list[FundingStep]:
    """
    Build a funding trail for a single tax lot by tracing backward through
    transactions related to the lot's tx_hash.

    Returns a list of FundingStep in chronological order (oldest first).
    """
    steps: list[FundingStep] = []
    seen_hashes: set[str] = set()

    # Start from the lot's acquisition transaction
    current_hash = lot["tx_hash"]
    token = lot["token"]
    amount = lot["amount"]
    cost_basis = lot["cost_basis_usd"]

    # Build a lookup from tx_hash to transaction
    tx_by_hash: dict[str, dict] = {}
    for tx in transactions:
        tx_by_hash[tx["tx_hash"]] = tx

    # Walk backward through the chain
    step_num = 0
    while current_hash and current_hash not in seen_hashes:
        seen_hashes.add(current_hash)
        tx = tx_by_hash.get(current_hash)
        if not tx:
            break

        step_num += 1
        tx_type = tx.get("tx_type", "unknown")
        chain = _extract_chain_from_tx(tx)
        protocol = _extract_protocol(tx)
        tx_date = _parse_date(tx.get("timestamp"))

        step = FundingStep(
            step_number=step_num,
            date=tx_date,
            action=_classify_action(tx_type),
            source=protocol,
            token=token,
            amount=amount,
            value_usd=cost_basis,
            tx_hash=current_hash,
            chain=chain,
        )
        steps.append(step)

        # Try to trace further back through raw_data
        raw = tx.get("raw_data")
        if isinstance(raw, dict):
            prev_hash = raw.get("prev_tx_hash")
            if prev_hash and prev_hash != current_hash:
                current_hash = prev_hash
                continue

        # No further backward link - stop
        break

    # Reverse so oldest is first (chronological order)
    steps.reverse()
    # Re-number in chronological order
    for i, step in enumerate(steps, start=1):
        step.step_number = i

    return steps


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def trace_holdings(
    db: Database,
    wallet_filter: list[str] | None = None,
    token_filter: list[str] | None = None,
) -> SourceOfFundsReport:
    """
    Trace the origin of all current holdings through transaction history.

    For each open tax lot (remaining > 0), traces backward through
    transactions to build a complete chain of custody.

    Args:
        db: Database instance.
        wallet_filter: Only include these wallet addresses (None = all).
        token_filter: Only include these tokens (None = all).

    Returns:
        SourceOfFundsReport with all holding origins.
    """
    lot_repo = TaxLotRepository(db)
    tx_repo = TransactionRepository(db)
    wallet_repo = WalletRepository(db)

    # Get all wallets
    wallets = wallet_repo.get_all()
    all_addresses = {w["address"] for w in wallets}

    if wallet_filter:
        filter_set = {a.lower() for a in wallet_filter}
        all_addresses = all_addresses & filter_set

    wallet_list = sorted(all_addresses)

    # Get all transactions (needed for backward tracing)
    all_transactions: list[dict] = []
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY timestamp"
        ).fetchall()
    all_transactions = [TransactionRepository._row_to_dict(r) for r in rows]

    # Get all open tax lots
    all_lots = lot_repo.get_all()
    open_lots = [
        lot for lot in all_lots
        if lot["remaining"] is not None and lot["remaining"] > Decimal("0")
    ]

    # Apply token filter
    if token_filter:
        token_set = {t.upper() for t in token_filter}
        open_lots = [lot for lot in open_lots if lot["token"].upper() in token_set]

    # Build holdings
    holdings: list[HoldingOrigin] = []
    total_value = Decimal("0")
    total_cost = Decimal("0")

    for lot in open_lots:
        token = lot["token"]
        remaining = lot["remaining"]
        source = lot.get("source", "unknown")
        acq_date = _parse_date(lot.get("acquisition_date"))
        cost_basis = lot["cost_basis_usd"]

        # Proportional cost for remaining amount
        if lot["amount"] > Decimal("0"):
            remaining_cost = (remaining / lot["amount"]) * cost_basis
        else:
            remaining_cost = Decimal("0")

        # Build the funding trail
        trail = _build_trail_for_lot(lot, all_transactions, all_addresses)

        # Determine wallet address from the transaction
        tx = next(
            (t for t in all_transactions if t["tx_hash"] == lot["tx_hash"]),
            None,
        )
        wallet_addr = ""
        chain = "unknown"
        if tx:
            chain = tx.get("chain", "unknown")
            raw = tx.get("raw_data")
            if isinstance(raw, dict):
                # Try to extract receiving address
                to_addr = raw.get("to_address", raw.get("to", ""))
                from_addr = raw.get("from_address", raw.get("from", ""))
                # The wallet that received this is likely in our known addresses
                if to_addr and to_addr.lower() in all_addresses:
                    wallet_addr = to_addr.lower()
                elif from_addr and from_addr.lower() in all_addresses:
                    wallet_addr = from_addr.lower()

        if not wallet_addr and wallet_list:
            wallet_addr = wallet_list[0]

        holding = HoldingOrigin(
            token=token,
            current_amount=remaining,
            current_value_usd=remaining_cost,  # cost-based; real-time price would be better
            wallet_address=wallet_addr,
            chain=chain,
            acquisition_method=_classify_acquisition_method(source),
            original_acquisition_date=acq_date,
            original_acquisition_cost=remaining_cost,
            funding_trail=trail,
        )
        holdings.append(holding)

        total_value += remaining_cost
        total_cost += remaining_cost

    return SourceOfFundsReport(
        generated_at=datetime.now(timezone.utc),
        wallet_addresses=wallet_list,
        holdings=holdings,
        total_portfolio_value=total_value,
        total_acquisition_cost=total_cost,
    )
