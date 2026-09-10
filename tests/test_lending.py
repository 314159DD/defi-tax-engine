"""
Tests for lending protocol detection (Aave, Compound).

Covers:
- Aave V3 deposit (USDC -> aUSDC)
- Aave V3 withdrawal (aUSDC -> USDC)
- Compound V3 deposit (cToken pattern)
- Lending liquidation detection
- Non-lending transactions not falsely matched
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.categorizer.protocols import AAVE_V3_POOL, COMPOUND_V3_USDC
from src.categorizer.rules.lending import (
    apply,
    is_lending_deposit,
    is_lending_liquidation,
    is_lending_withdraw,
)
from src.importers.models import AssetTransfer, Transaction

_TS = datetime(2025, 6, 1, tzinfo=timezone.utc)
USER = "0xuser000000000000000000000000000000000001"


def _a(symbol: str, amount: str = "1") -> AssetTransfer:
    return AssetTransfer(token_symbol=symbol, amount=Decimal(amount))


def _tx(
    to_addr: str = AAVE_V3_POOL,
    from_addr: str = USER,
    assets_in: list[AssetTransfer] | None = None,
    assets_out: list[AssetTransfer] | None = None,
    protocol: str | None = None,
    raw_data: dict | None = None,
) -> Transaction:
    return Transaction(
        tx_hash="0xlendingtest",
        chain="ethereum",
        block_number=1,
        timestamp=_TS,
        from_address=from_addr,
        to_address=to_addr,
        tx_type="unknown",
        assets_in=assets_in or [],
        assets_out=assets_out or [],
        fee=None,
        protocol=protocol,
        raw_data=raw_data or {},
    )


class TestLendingDeposit:
    """Test lending deposit detection."""

    def test_aave_v3_deposit(self) -> None:
        """Deposit USDC into Aave V3, receive aEthUSDC."""
        tx = _tx(
            to_addr=AAVE_V3_POOL,
            assets_out=[_a("USDC", "5000")],
            assets_in=[_a("aEthUSDC", "5000")],
        )
        assert is_lending_deposit(tx) is True
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "lending_deposit"
        assert result.protocol == "Aave V3"

    def test_compound_v3_deposit(self) -> None:
        """Deposit USDC into Compound V3, receive cUSDC."""
        tx = _tx(
            to_addr=COMPOUND_V3_USDC,
            assets_out=[_a("USDC", "10000")],
            assets_in=[_a("cUSDC", "10000")],
        )
        assert is_lending_deposit(tx) is True
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "lending_deposit"

    def test_aave_deposit_via_protocol_name(self) -> None:
        """Deposit detected by protocol name."""
        tx = _tx(
            to_addr="0x1234567890123456789012345678901234567890",
            assets_out=[_a("WETH", "10")],
            assets_in=[_a("aWETH", "10")],
            protocol="Aave V2",
        )
        assert is_lending_deposit(tx) is True

    def test_no_receipt_token_not_deposit(self) -> None:
        """Non-aToken/cToken in - not a lending deposit."""
        tx = _tx(
            assets_out=[_a("USDC", "1000")],
            assets_in=[_a("DAI", "1000")],
        )
        assert is_lending_deposit(tx) is False


class TestLendingWithdraw:
    """Test lending withdrawal detection."""

    def test_aave_v3_withdraw(self) -> None:
        """Withdraw from Aave: burn aEthUSDC, receive USDC."""
        tx = _tx(
            to_addr=AAVE_V3_POOL,
            assets_out=[_a("aEthUSDC", "5100")],  # includes accrued interest
            assets_in=[_a("USDC", "5100")],
        )
        assert is_lending_withdraw(tx) is True
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "lending_withdraw"

    def test_compound_withdraw(self) -> None:
        """Withdraw from Compound: burn cUSDC, receive USDC."""
        tx = _tx(
            to_addr=COMPOUND_V3_USDC,
            assets_out=[_a("cUSDC", "9500")],
            assets_in=[_a("USDC", "10200")],  # exchange rate appreciation
        )
        assert is_lending_withdraw(tx) is True

    def test_withdraw_from_lending_contract(self) -> None:
        """from_address is lending pool (receive side)."""
        tx = _tx(
            to_addr=USER,
            from_addr=AAVE_V3_POOL,
            assets_out=[_a("aWETH", "5")],
            assets_in=[_a("WETH", "5")],
        )
        assert is_lending_withdraw(tx) is True


class TestLendingLiquidation:
    """Test liquidation detection."""

    def test_liquidation_by_method_name(self) -> None:
        """Liquidation detected from functionName in raw_data."""
        tx = _tx(
            to_addr=AAVE_V3_POOL,
            assets_in=[_a("USDC", "4000")],
            raw_data={"functionName": "liquidationCall"},
        )
        assert is_lending_liquidation(tx) is True
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "lending_liquidation"

    def test_no_liquidation_without_method(self) -> None:
        """Without liquidation method, do not classify as liquidation."""
        tx = _tx(
            to_addr=AAVE_V3_POOL,
            assets_in=[_a("USDC", "4000")],
        )
        assert is_lending_liquidation(tx) is False


class TestLendingNonMatch:
    """Ensure non-lending transactions are not matched."""

    def test_regular_swap(self) -> None:
        tx = _tx(
            to_addr="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            assets_out=[_a("ETH", "1")],
            assets_in=[_a("USDC", "2000")],
        )
        result = apply(tx)
        assert result is None

    def test_no_assets(self) -> None:
        tx = _tx()
        result = apply(tx)
        assert result is None
