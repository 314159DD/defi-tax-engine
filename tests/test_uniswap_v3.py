"""
Tests for Uniswap V3 concentrated liquidity position detection.

Covers:
- Mint position via NonfungiblePositionManager
- Increase liquidity to existing position
- Decrease liquidity (partial / full)
- Collect fees
- Burn position
- Heuristic detection when method signatures are unavailable
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.categorizer.rules.uniswap_v3 import (
    UNI_V3_POSITION_MANAGER,
    apply,
    is_uni_v3,
)
from src.importers.models import AssetTransfer, Transaction

_TS = datetime(2025, 6, 1, tzinfo=timezone.utc)
USER = "0xuser000000000000000000000000000000000001"


def _a(symbol: str, amount: str = "1") -> AssetTransfer:
    return AssetTransfer(token_symbol=symbol, amount=Decimal(amount))


def _tx(
    to_addr: str = UNI_V3_POSITION_MANAGER,
    assets_in: list[AssetTransfer] | None = None,
    assets_out: list[AssetTransfer] | None = None,
    raw_data: dict | None = None,
) -> Transaction:
    return Transaction(
        tx_hash="0xuniv3test",
        chain="ethereum",
        block_number=1,
        timestamp=_TS,
        from_address=USER,
        to_address=to_addr,
        tx_type="unknown",
        assets_in=assets_in or [],
        assets_out=assets_out or [],
        fee=None,
        protocol=None,
        raw_data=raw_data or {},
    )


class TestUniswapV3Detection:
    """Test is_uni_v3 detection."""

    def test_position_manager_address(self) -> None:
        tx = _tx(to_addr=UNI_V3_POSITION_MANAGER)
        assert is_uni_v3(tx) is True

    def test_non_uni_v3_address(self) -> None:
        tx = _tx(to_addr="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        assert is_uni_v3(tx) is False

    def test_protocol_name_does_not_match_without_address(self) -> None:
        tx = _tx(to_addr="0x1234567890123456789012345678901234567890")
        tx = Transaction(
            tx_hash=tx.tx_hash, chain=tx.chain, block_number=tx.block_number,
            timestamp=tx.timestamp, from_address=tx.from_address,
            to_address=tx.to_address, tx_type=tx.tx_type,
            assets_in=tx.assets_in, assets_out=tx.assets_out,
            fee=tx.fee, protocol="Uniswap V3", raw_data=tx.raw_data,
        )
        # Protocol name alone is not enough - need the position manager address
        assert is_uni_v3(tx) is False


class TestUniswapV3Mint:
    """Test mint position detection."""

    def test_mint_with_method_sig(self) -> None:
        """Mint detected via method signature 0x88316456."""
        tx = _tx(
            assets_out=[_a("ETH", "1"), _a("USDC", "2000")],
            raw_data={"input": "0x88316456000000000000000000"},
        )
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "uni_v3_mint"
        assert result.protocol == "Uniswap V3"

    def test_mint_heuristic_send_only(self) -> None:
        """Mint detected via heuristic: send tokens, receive nothing."""
        tx = _tx(
            assets_out=[_a("ETH", "5"), _a("USDC", "10000")],
        )
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "uni_v3_mint"

    def test_increase_liquidity(self) -> None:
        """IncreaseLiquidity detected via method signature."""
        tx = _tx(
            assets_out=[_a("ETH", "0.5"), _a("USDC", "1000")],
            raw_data={"input": "0x219f5d17000000000000000000"},
        )
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "uni_v3_increase"


class TestUniswapV3Collect:
    """Test fee collection detection."""

    def test_collect_with_method_sig(self) -> None:
        tx = _tx(
            assets_in=[_a("ETH", "0.01"), _a("USDC", "20")],
            raw_data={"input": "0xfc6f7865000000000000000000"},
        )
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "uni_v3_collect"


class TestUniswapV3Decrease:
    """Test decrease liquidity detection."""

    def test_decrease_with_method_sig(self) -> None:
        tx = _tx(
            assets_in=[_a("ETH", "1"), _a("USDC", "2000")],
            raw_data={"input": "0x0c49ccbe000000000000000000"},
        )
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "uni_v3_decrease"

    def test_decrease_heuristic_receive_only(self) -> None:
        """Receive tokens from position manager without method sig."""
        tx = _tx(
            assets_in=[_a("ETH", "2"), _a("USDC", "4000")],
        )
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "uni_v3_decrease"


class TestUniswapV3Burn:
    """Test burn position detection."""

    def test_burn_with_method_sig(self) -> None:
        tx = _tx(raw_data={"input": "0x42966c68000000000000000000"})
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "uni_v3_burn"

    def test_burn_heuristic_no_assets(self) -> None:
        """No asset movement at all = burn."""
        tx = _tx()
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "uni_v3_burn"


class TestNonUniV3:
    """Ensure non-Uni V3 transactions are not matched."""

    def test_random_contract(self) -> None:
        tx = _tx(to_addr="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        result = apply(tx)
        assert result is None
