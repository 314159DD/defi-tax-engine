"""
Tests for spam token filter.

Covers:
- Known spam contract detection
- Token name heuristic detection (URL patterns, "Visit", "Claim at")
- Zero-value transfer detection
- Dust amount detection
- Legitimate transactions not falsely flagged
- SpamFilter.filter_spam partitioning
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.categorizer.spam import SpamFilter
from src.data.spam_tokens import KNOWN_SPAM_CONTRACTS
from src.importers.models import AssetTransfer, Transaction

_TS = datetime(2025, 6, 1, tzinfo=timezone.utc)
USER = "0xuser000000000000000000000000000000000001"
RANDOM_ADDR = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

# Grab one known spam address for testing
_SPAM_ADDR = next(iter(KNOWN_SPAM_CONTRACTS))


def _a(
    symbol: str,
    amount: str = "1",
    usd_value: str | None = None,
    token_address: str | None = None,
) -> AssetTransfer:
    return AssetTransfer(
        token_symbol=symbol,
        amount=Decimal(amount),
        token_address=token_address,
        usd_value=Decimal(usd_value) if usd_value else None,
    )


def _tx(
    from_addr: str = RANDOM_ADDR,
    to_addr: str = USER,
    assets_in: list[AssetTransfer] | None = None,
    assets_out: list[AssetTransfer] | None = None,
) -> Transaction:
    return Transaction(
        tx_hash="0xspamtest",
        chain="ethereum",
        block_number=1,
        timestamp=_TS,
        from_address=from_addr,
        to_address=to_addr,
        tx_type="unknown",
        assets_in=assets_in or [],
        assets_out=assets_out or [],
        fee=None,
        protocol=None,
        raw_data={},
    )


class TestKnownSpamContracts:
    """Test detection via known spam contract addresses."""

    def test_known_spam_token_address(self) -> None:
        """Token with a known spam contract address is flagged."""
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("SCAM", "1000", token_address=_SPAM_ADDR)])
        assert sf.is_spam(tx) is True

    def test_known_spam_sender(self) -> None:
        """Transaction from a known spam address is flagged."""
        sf = SpamFilter()
        tx = _tx(from_addr=_SPAM_ADDR, assets_in=[_a("SCAM", "1000")])
        assert sf.is_spam(tx) is True

    def test_extra_spam_contracts(self) -> None:
        """User-supplied extra spam addresses are respected."""
        custom_spam = "0xcustom_spam_address_1234567890abcdef1234"
        sf = SpamFilter(extra_spam_contracts={custom_spam})
        tx = _tx(from_addr=custom_spam, assets_in=[_a("TOKEN", "100")])
        assert sf.is_spam(tx) is True


class TestSpamNameHeuristics:
    """Test token name pattern matching."""

    def test_visit_url_pattern(self) -> None:
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("Visit scam.com", "1000")])
        assert sf.is_spam(tx) is True

    def test_claim_at_pattern(self) -> None:
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("Claim at fakesite.xyz", "500")])
        assert sf.is_spam(tx) is True

    def test_url_in_name(self) -> None:
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("https://phishing.com", "1")])
        assert sf.is_spam(tx) is True

    def test_domain_in_name(self) -> None:
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("FreeTokens.xyz", "1000")])
        assert sf.is_spam(tx) is True

    def test_legitimate_name_not_flagged(self) -> None:
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("UNI", "100")])
        assert sf.is_spam(tx) is False


class TestZeroValueTransfer:
    """Test zero-value transfer detection."""

    def test_all_zero_amounts(self) -> None:
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("SCAM", "0"), _a("FAKE", "0")])
        assert sf.is_spam(tx) is True

    def test_mixed_amounts_not_flagged(self) -> None:
        """If any transfer has non-zero amount, don't flag."""
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("ETH", "1"), _a("SCAM", "0")])
        assert sf.is_spam(tx) is False


class TestDustAmount:
    """Test dust amount detection."""

    def test_dust_airdrop(self) -> None:
        """Tiny incoming value with no outgoing = spam airdrop."""
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("FAKE", "0.000001", usd_value="0.001")])
        assert sf.is_spam(tx) is True

    def test_small_legitimate_airdrop(self) -> None:
        """Small but above threshold airdrop should not be flagged."""
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("UNI", "0.1", usd_value="0.50")])
        assert sf.is_spam(tx) is False

    def test_dust_with_outgoing_not_flagged(self) -> None:
        """If user sent something, don't flag as dust spam."""
        sf = SpamFilter()
        tx = _tx(
            assets_in=[_a("SCAM", "0.001", usd_value="0.001")],
            assets_out=[_a("ETH", "0.01")],
        )
        assert sf.is_spam(tx) is False

    def test_unknown_value_not_flagged(self) -> None:
        """If USD value is unknown, don't assume spam."""
        sf = SpamFilter()
        tx = _tx(assets_in=[_a("UNKNOWN", "0.001")])
        assert sf.is_spam(tx) is False


class TestFilterSpam:
    """Test filter_spam partitioning method."""

    def test_partition(self) -> None:
        sf = SpamFilter()
        txs = [
            _tx(assets_in=[_a("ETH", "1", usd_value="2000")]),    # clean
            _tx(assets_in=[_a("Visit scam.com", "1000")]),          # spam
            _tx(assets_in=[_a("UNI", "50", usd_value="500")]),     # clean
        ]
        clean, spam = sf.filter_spam(txs)
        assert len(clean) == 2
        assert len(spam) == 1
        assert spam[0].tx_type == "spam"
        assert spam[0].raw_data.get("spam") is True
