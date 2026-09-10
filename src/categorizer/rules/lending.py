"""
Lending protocol deposit/withdrawal/liquidation detection.

Lending protocols (Aave, Compound) allow users to deposit collateral and
borrow assets.  Interest accrues via rebasing aTokens (Aave) or appreciating
cToken exchange rates (Compound).

Tax treatment:
- Deposit (collateral): NOT taxable. Cost basis carries over.
- Withdrawal: gain = (withdrawn - deposited) at FMV. Interest portion = income.
- Borrowing: NOT taxable (it is a loan, not income).
- Liquidation: forced sale at market price. Loss = (proceeds - cost basis).
- Interest accrual (aToken rebase): income event at FMV of increase.

Supported protocols:
- Aave V2/V3 (aToken / Pool contract)
- Compound V2 (cToken / Comptroller)
- Compound V3 (Comet contracts)
"""
from __future__ import annotations

import re

from src.categorizer.protocols import (
    AAVE_V2_POOL,
    AAVE_V3_POOL,
    COMPOUND_V2_COMPTROLLER,
    COMPOUND_V3_USDC,
    resolve_protocol,
)
from src.importers.models import AssetTransfer, Transaction

# ── Contract address sets ────────────────────────────────────────────────────
AAVE_POOL_ADDRESSES: frozenset[str] = frozenset({
    AAVE_V2_POOL,
    AAVE_V3_POOL,
})

COMPOUND_ADDRESSES: frozenset[str] = frozenset({
    COMPOUND_V2_COMPTROLLER,
    COMPOUND_V3_USDC,
})

LENDING_ADDRESSES: frozenset[str] = AAVE_POOL_ADDRESSES | COMPOUND_ADDRESSES

# ── aToken / cToken detection ────────────────────────────────────────────────
_ATOKEN_RE = re.compile(r"(?i)^a[A-Z]")          # aUSDC, aWETH, aDAI
_ATOKEN_V3_RE = re.compile(r"(?i)^aEth[A-Z]")    # aEthUSDC (Aave V3 on ETH)
_CTOKEN_RE = re.compile(r"(?i)^c[A-Z]")          # cUSDC, cETH, cDAI

_LENDING_TOKEN_PATTERNS = [_ATOKEN_RE, _ATOKEN_V3_RE, _CTOKEN_RE]


def _is_lending_receipt_token(transfer: AssetTransfer) -> bool:
    """Return True if the token looks like an aToken or cToken."""
    sym = transfer.token_symbol
    return any(p.search(sym) for p in _LENDING_TOKEN_PATTERNS)


def _to_lending_contract(tx: Transaction) -> bool:
    """Return True if to_address is a known lending pool."""
    return tx.to_address.lower() in LENDING_ADDRESSES


def _from_lending_contract(tx: Transaction) -> bool:
    """Return True if from_address is a known lending pool."""
    return tx.from_address.lower() in LENDING_ADDRESSES


def _protocol_is_lending(tx: Transaction) -> bool:
    """Return True if protocol name indicates a lending protocol."""
    if not tx.protocol:
        return False
    lower = tx.protocol.lower()
    return any(kw in lower for kw in ("aave", "compound", "lending", "morpho", "spark"))


def is_lending_deposit(tx: Transaction) -> bool:
    """
    Detect lending deposit: user sends underlying, receives aToken/cToken.

    Patterns:
    1. assets_out has underlying, assets_in has aToken/cToken
    2. Interacts with known lending contract
    """
    if not tx.assets_in or not tx.assets_out:
        return False

    has_receipt_in = any(_is_lending_receipt_token(t) for t in tx.assets_in)
    has_receipt_out = any(_is_lending_receipt_token(t) for t in tx.assets_out)

    # Deposit: send underlying, receive aToken/cToken
    if has_receipt_in and not has_receipt_out:
        if _to_lending_contract(tx) or _protocol_is_lending(tx):
            return True

    return False


def is_lending_withdraw(tx: Transaction) -> bool:
    """
    Detect lending withdrawal: user burns aToken/cToken, receives underlying.

    Patterns:
    1. assets_out has aToken/cToken, assets_in has underlying
    2. Interacts with known lending contract
    """
    if not tx.assets_in or not tx.assets_out:
        return False

    has_receipt_in = any(_is_lending_receipt_token(t) for t in tx.assets_in)
    has_receipt_out = any(_is_lending_receipt_token(t) for t in tx.assets_out)

    # Withdraw: send aToken/cToken, receive underlying
    if has_receipt_out and not has_receipt_in:
        if _to_lending_contract(tx) or _from_lending_contract(tx) or _protocol_is_lending(tx):
            return True

    return False


def is_lending_liquidation(tx: Transaction) -> bool:
    """
    Detect liquidation: forced closure of under-collateralized position.

    Heuristic: interaction with lending contract where the from_address is NOT
    the user (a liquidator calls the contract on their behalf).  This is
    hard to detect purely from normalized data - we flag conservatively.
    """
    if not tx.assets_in:
        return False

    # Liquidation often shows as receiving collateral back with no send,
    # from a lending contract, with a 'liquidation' method in raw data
    method = tx.raw_data.get("method", "") or tx.raw_data.get("functionName", "")
    if isinstance(method, str) and "liquidat" in method.lower():
        if _to_lending_contract(tx) or _from_lending_contract(tx) or _protocol_is_lending(tx):
            return True

    return False


def apply(tx: Transaction) -> Transaction | None:
    """
    Classify as 'lending_deposit', 'lending_withdraw', or 'lending_liquidation'.
    Returns None if the rule does not apply.
    """
    protocol = tx.protocol or resolve_protocol(tx.to_address)

    if is_lending_liquidation(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="lending_liquidation",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "Lending",
            raw_data=tx.raw_data,
        )

    if is_lending_deposit(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="lending_deposit",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "Lending",
            raw_data=tx.raw_data,
        )

    if is_lending_withdraw(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="lending_withdraw",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "Lending",
            raw_data=tx.raw_data,
        )

    return None
