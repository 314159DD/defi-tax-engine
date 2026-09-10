"""
Tests for vault deposit/withdrawal detection.

Covers:
- Yearn vault deposit (DAI -> yvDAI)
- Yearn vault withdrawal (yvDAI -> DAI)
- Beefy vault deposit (mooToken pattern)
- Convex vault detection
- Non-vault transactions not falsely matched
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.categorizer.rules.vault import (
    VAULT_ADDRESSES,
    apply,
    is_vault_deposit,
    is_vault_withdraw,
)
from src.importers.models import AssetTransfer, Transaction

_TS = datetime(2025, 6, 1, tzinfo=timezone.utc)
USER = "0xuser000000000000000000000000000000000001"
YEARN_YVDAI = "0x19d3364a399d251e894ac732651be8b0e4e85001"


def _a(symbol: str, amount: str = "1") -> AssetTransfer:
    return AssetTransfer(token_symbol=symbol, amount=Decimal(amount))


def _tx(
    to_addr: str = YEARN_YVDAI,
    assets_in: list[AssetTransfer] | None = None,
    assets_out: list[AssetTransfer] | None = None,
    protocol: str | None = None,
) -> Transaction:
    return Transaction(
        tx_hash="0xvaulttest",
        chain="ethereum",
        block_number=1,
        timestamp=_TS,
        from_address=USER,
        to_address=to_addr,
        tx_type="unknown",
        assets_in=assets_in or [],
        assets_out=assets_out or [],
        fee=None,
        protocol=protocol,
        raw_data={},
    )


class TestVaultDeposit:
    """Test vault deposit detection."""

    def test_yearn_deposit(self) -> None:
        """Deposit DAI into yvDAI vault."""
        tx = _tx(
            to_addr=YEARN_YVDAI,
            assets_out=[_a("DAI", "1000")],
            assets_in=[_a("yvDAI", "980")],
        )
        assert is_vault_deposit(tx) is True
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "vault_deposit"
        assert result.protocol == "Yearn"

    def test_beefy_deposit(self) -> None:
        """Deposit into Beefy vault (mooToken pattern)."""
        tx = _tx(
            to_addr=list(VAULT_ADDRESSES)[0],
            assets_out=[_a("USDC", "5000")],
            assets_in=[_a("mooCurveUSDC", "4900")],
            protocol="Beefy",
        )
        assert is_vault_deposit(tx) is True
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "vault_deposit"

    def test_convex_deposit(self) -> None:
        """Deposit into Convex (cvxToken pattern)."""
        tx = _tx(
            to_addr="0xf403c135812408bfbe8713b5a23a04b3d48aae31",
            assets_out=[_a("CRV", "1000")],
            assets_in=[_a("cvxCRV", "1000")],
            protocol="Convex",
        )
        assert is_vault_deposit(tx) is True

    def test_no_vault_token_not_deposit(self) -> None:
        """Non-vault token should not match."""
        tx = _tx(
            assets_out=[_a("DAI", "1000")],
            assets_in=[_a("USDC", "1000")],
        )
        assert is_vault_deposit(tx) is False


class TestVaultWithdraw:
    """Test vault withdrawal detection."""

    def test_yearn_withdraw(self) -> None:
        """Withdraw from yvDAI vault."""
        tx = _tx(
            to_addr=YEARN_YVDAI,
            assets_out=[_a("yvDAI", "980")],
            assets_in=[_a("DAI", "1050")],  # 5% yield
        )
        assert is_vault_withdraw(tx) is True
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "vault_withdraw"

    def test_beefy_withdraw(self) -> None:
        """Withdraw from Beefy vault."""
        tx = _tx(
            assets_out=[_a("mooCurveDAI", "900")],
            assets_in=[_a("DAI", "1000")],
            protocol="Beefy",
        )
        assert is_vault_withdraw(tx) is True

    def test_partial_withdraw(self) -> None:
        """Partial withdrawal from vault."""
        tx = _tx(
            to_addr=YEARN_YVDAI,
            assets_out=[_a("yvDAI", "500")],
            assets_in=[_a("DAI", "525")],
        )
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "vault_withdraw"


class TestVaultNonMatch:
    """Ensure non-vault transactions return None."""

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
