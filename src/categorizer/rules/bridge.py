"""
Bridge transaction detection rule.

A bridge moves assets cross-chain. It is NOT a taxable event - the cost basis
carries over to the destination chain. The original send is flagged as 'bridge'.

Enhanced detection (Sprint 4.1):
- Expanded bridge protocol list: Across, Stargate, Hop, Synapse, Orbiter, Wormhole
- Cross-chain matching: same token, amount within 2% tolerance, timing within 30min
- Bridge fee = deductible expense (added to cost basis of received tokens)
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from src.categorizer.protocols import BRIDGE_ADDRESSES, resolve_protocol
from src.data.token_pairs import is_equivalent
from src.importers.models import Transaction

# ── Bridge matching tolerance ────────────────────────────────────────────────
_AMOUNT_TOLERANCE = Decimal("0.02")   # 2% tolerance for bridge fees
_TIME_TOLERANCE = timedelta(minutes=30)


def is_bridge(tx: Transaction) -> bool:
    """
    Return True if this transaction interacts with a known bridge contract.

    Detection strategy:
    1. to_address is a known bridge contract address
    2. from_address is a known bridge contract (receiving side)
    3. Protocol name contains bridge-related keywords
    4. raw_data contains bridge method signatures
    """
    to_addr = tx.to_address.lower()
    from_addr = tx.from_address.lower()

    if to_addr in BRIDGE_ADDRESSES:
        return True
    if from_addr in BRIDGE_ADDRESSES:
        return True

    # Check protocol name already set
    if tx.protocol and any(
        kw in tx.protocol.lower()
        for kw in ("bridge", "hop", "stargate", "across", "synapse", "celer",
                    "multichain", "orbiter", "wormhole", "layerzero")
    ):
        return True

    # Check raw_data for bridge-related function names
    method = tx.raw_data.get("functionName", "") or tx.raw_data.get("method", "")
    if isinstance(method, str) and any(
        kw in method.lower()
        for kw in ("deposit", "bridge", "relay", "sendmessage", "fillrelay")
    ):
        if to_addr in BRIDGE_ADDRESSES or from_addr in BRIDGE_ADDRESSES:
            return True

    return False


def match_bridge_pair(
    source_tx: Transaction,
    dest_tx: Transaction,
) -> bool:
    """
    Determine if two transactions form a bridge pair (source chain -> dest chain).

    Matching criteria:
    1. Different chains
    2. Same token (or canonical equivalent, e.g. USDC.e <-> USDC)
    3. Amount within 2% tolerance (bridge takes a fee)
    4. Timing within 30 minutes

    Args:
        source_tx: The outgoing transaction on the source chain.
        dest_tx: The incoming transaction on the destination chain.

    Returns:
        True if the transactions are a matched bridge pair.
    """
    # Must be on different chains
    if source_tx.chain == dest_tx.chain:
        return False

    # Must have outgoing on source and incoming on destination
    if not source_tx.assets_out or not dest_tx.assets_in:
        return False

    # Check timing
    time_diff = abs(dest_tx.timestamp - source_tx.timestamp)
    if time_diff > _TIME_TOLERANCE:
        return False

    # Check token equivalence and amount tolerance
    for out_asset in source_tx.assets_out:
        for in_asset in dest_tx.assets_in:
            if is_equivalent(out_asset.token_symbol, in_asset.token_symbol):
                if out_asset.amount > Decimal("0") and in_asset.amount > Decimal("0"):
                    ratio = abs(out_asset.amount - in_asset.amount) / out_asset.amount
                    if ratio <= _AMOUNT_TOLERANCE:
                        return True

    return False


def calculate_bridge_fee(source_tx: Transaction, dest_tx: Transaction) -> Decimal:
    """
    Calculate the bridge fee as the difference between sent and received amounts.

    Returns Decimal("0") if amounts cannot be compared.
    """
    if not source_tx.assets_out or not dest_tx.assets_in:
        return Decimal("0")

    for out_asset in source_tx.assets_out:
        for in_asset in dest_tx.assets_in:
            if is_equivalent(out_asset.token_symbol, in_asset.token_symbol):
                fee = out_asset.amount - in_asset.amount
                return max(fee, Decimal("0"))

    return Decimal("0")


def apply(tx: Transaction) -> Transaction | None:
    """
    If this is a bridge transaction, set tx_type to 'bridge' and return updated tx.
    Returns None if rule does not apply.
    """
    if not is_bridge(tx):
        return None

    protocol = tx.protocol or resolve_protocol(tx.to_address) or resolve_protocol(tx.from_address) or "Bridge"
    return Transaction(
        tx_hash=tx.tx_hash,
        chain=tx.chain,
        block_number=tx.block_number,
        timestamp=tx.timestamp,
        from_address=tx.from_address,
        to_address=tx.to_address,
        tx_type="bridge",
        assets_in=tx.assets_in,
        assets_out=tx.assets_out,
        fee=tx.fee,
        protocol=protocol,
        raw_data=tx.raw_data,
    )
