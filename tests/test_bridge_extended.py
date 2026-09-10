"""
Tests for extended bridge detection (Sprint 4.1).

Covers:
- Across bridge detection
- Stargate bridge detection
- Hop Protocol bridge detection
- Orbiter / Wormhole detection
- Bridge pair matching (cross-chain, same token, amount tolerance, timing)
- Bridge fee calculation
- Non-bridge transactions not falsely matched
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.categorizer.protocols import (
    ACROSS_BRIDGE,
    HOP_ETH_BRIDGE,
    ORBITER_BRIDGE,
    STARGATE_ROUTER,
    SYNAPSE_BRIDGE,
    WORMHOLE_BRIDGE,
)
from src.categorizer.rules.bridge import apply, calculate_bridge_fee, is_bridge, match_bridge_pair
from src.importers.models import AssetTransfer, Transaction

_TS = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
USER = "0xuser000000000000000000000000000000000001"


def _a(symbol: str, amount: str = "1") -> AssetTransfer:
    return AssetTransfer(token_symbol=symbol, amount=Decimal(amount))


def _tx(
    to_addr: str = ACROSS_BRIDGE,
    from_addr: str = USER,
    chain: str = "ethereum",
    assets_in: list[AssetTransfer] | None = None,
    assets_out: list[AssetTransfer] | None = None,
    protocol: str | None = None,
    timestamp: datetime = _TS,
    raw_data: dict | None = None,
) -> Transaction:
    return Transaction(
        tx_hash="0xbridgetest",
        chain=chain,
        block_number=1,
        timestamp=timestamp,
        from_address=from_addr,
        to_address=to_addr,
        tx_type="unknown",
        assets_in=assets_in or [],
        assets_out=assets_out or [],
        fee=None,
        protocol=protocol,
        raw_data=raw_data or {},
    )


class TestBridgeDetection:
    """Test is_bridge detection for new bridge protocols."""

    def test_across_bridge(self) -> None:
        tx = _tx(to_addr=ACROSS_BRIDGE)
        assert is_bridge(tx) is True

    def test_stargate_router(self) -> None:
        tx = _tx(to_addr=STARGATE_ROUTER)
        assert is_bridge(tx) is True

    def test_hop_bridge(self) -> None:
        tx = _tx(to_addr=HOP_ETH_BRIDGE)
        assert is_bridge(tx) is True

    def test_synapse_bridge(self) -> None:
        tx = _tx(to_addr=SYNAPSE_BRIDGE)
        assert is_bridge(tx) is True

    def test_orbiter_bridge(self) -> None:
        tx = _tx(to_addr=ORBITER_BRIDGE)
        assert is_bridge(tx) is True

    def test_wormhole_bridge(self) -> None:
        tx = _tx(to_addr=WORMHOLE_BRIDGE)
        assert is_bridge(tx) is True

    def test_protocol_name_wormhole(self) -> None:
        tx = _tx(
            to_addr="0x1234567890123456789012345678901234567890",
            protocol="Wormhole",
        )
        assert is_bridge(tx) is True

    def test_receive_from_bridge(self) -> None:
        """Bridge receive: from_address is a bridge contract."""
        tx = _tx(
            to_addr=USER,
            from_addr=ACROSS_BRIDGE,
        )
        assert is_bridge(tx) is True


class TestBridgeApply:
    """Test bridge.apply sets correct tx_type."""

    def test_bridge_categorized(self) -> None:
        tx = _tx(
            to_addr=ACROSS_BRIDGE,
            assets_out=[_a("ETH", "1")],
        )
        result = apply(tx)
        assert result is not None
        assert result.tx_type == "bridge"
        assert result.protocol == "Across"

    def test_non_bridge_returns_none(self) -> None:
        tx = _tx(to_addr="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        result = apply(tx)
        assert result is None


class TestBridgePairMatching:
    """Test cross-chain bridge pair matching."""

    def test_matching_pair(self) -> None:
        """Same token, similar amount, different chains, within time window."""
        source = _tx(
            chain="ethereum",
            to_addr=ACROSS_BRIDGE,
            assets_out=[_a("ETH", "1.0")],
            timestamp=_TS,
        )
        dest = _tx(
            chain="arbitrum",
            from_addr=ACROSS_BRIDGE,
            assets_in=[_a("ETH", "0.999")],  # ~0.1% bridge fee
            timestamp=_TS + timedelta(minutes=2),
        )
        assert match_bridge_pair(source, dest) is True

    def test_equivalent_tokens(self) -> None:
        """USDC.e on Polygon matches USDC on Ethereum."""
        source = _tx(
            chain="ethereum",
            assets_out=[_a("USDC", "1000")],
            timestamp=_TS,
        )
        dest = _tx(
            chain="polygon",
            assets_in=[_a("USDC.E", "998")],  # within 2%
            timestamp=_TS + timedelta(minutes=5),
        )
        assert match_bridge_pair(source, dest) is True

    def test_amount_exceeds_tolerance(self) -> None:
        """Reject pair when amount difference > 2%."""
        source = _tx(
            chain="ethereum",
            assets_out=[_a("ETH", "1.0")],
            timestamp=_TS,
        )
        dest = _tx(
            chain="arbitrum",
            assets_in=[_a("ETH", "0.95")],  # 5% difference
            timestamp=_TS + timedelta(minutes=2),
        )
        assert match_bridge_pair(source, dest) is False

    def test_timing_exceeds_window(self) -> None:
        """Reject pair when timing > 30 minutes."""
        source = _tx(
            chain="ethereum",
            assets_out=[_a("ETH", "1.0")],
            timestamp=_TS,
        )
        dest = _tx(
            chain="arbitrum",
            assets_in=[_a("ETH", "0.999")],
            timestamp=_TS + timedelta(hours=2),
        )
        assert match_bridge_pair(source, dest) is False

    def test_same_chain_rejected(self) -> None:
        """Reject pair on same chain."""
        source = _tx(
            chain="ethereum",
            assets_out=[_a("ETH", "1.0")],
        )
        dest = _tx(
            chain="ethereum",
            assets_in=[_a("ETH", "0.999")],
        )
        assert match_bridge_pair(source, dest) is False


class TestBridgeFee:
    """Test bridge fee calculation."""

    def test_fee_calculation(self) -> None:
        source = _tx(
            chain="ethereum",
            assets_out=[_a("ETH", "1.0")],
        )
        dest = _tx(
            chain="arbitrum",
            assets_in=[_a("ETH", "0.995")],
        )
        fee = calculate_bridge_fee(source, dest)
        assert fee == Decimal("0.005")

    def test_no_fee_when_amounts_match(self) -> None:
        source = _tx(chain="ethereum", assets_out=[_a("ETH", "1.0")])
        dest = _tx(chain="arbitrum", assets_in=[_a("ETH", "1.0")])
        fee = calculate_bridge_fee(source, dest)
        assert fee == Decimal("0")
