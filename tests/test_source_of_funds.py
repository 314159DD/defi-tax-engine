"""
Tests for Source of Funds report (Sprint 5.5).

Covers:
  - Simple trace: exchange purchase -> hold
  - Multi-step: exchange purchase -> bridge -> swap -> hold
  - Staking reward origin
  - Airdrop origin
  - Multiple holdings with different origins
  - CSV generation format
  - Text report generation
  - Empty holdings (all sold)
  - All monetary values as Decimal
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.reports.source_of_funds import (
    FundingStep,
    HoldingOrigin,
    SourceOfFundsReport,
    trace_holdings,
)
from src.reports.source_of_funds_pdf import (
    generate_source_of_funds_csv,
    generate_source_of_funds_text,
)
from src.storage.database import (
    Database,
    TaxLotRepository,
    TransactionRepository,
    WalletRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_wallet(db: Database, address: str, chain: str = "ethereum") -> None:
    repo = WalletRepository(db)
    repo.add(address, chain)


def _add_transaction(
    db: Database,
    tx_hash: str,
    chain: str = "ethereum",
    timestamp: str = "2025-01-15T10:00:00+00:00",
    tx_type: str = "swap",
    protocol: str | None = None,
    raw_data: dict | None = None,
) -> None:
    repo = TransactionRepository(db)
    repo.upsert(
        tx_hash=tx_hash,
        chain=chain,
        timestamp=timestamp,
        tx_type=tx_type,
        protocol=protocol,
        raw_data=raw_data or {},
    )


def _add_lot(
    db: Database,
    token: str,
    amount: str,
    cost_basis: str,
    acquisition_date: str = "2025-01-15T10:00:00+00:00",
    remaining: str | None = None,
    source: str = "swap",
    tx_hash: str = "0xtest",
) -> str:
    repo = TaxLotRepository(db)
    lot_id = repo.insert(
        token=token,
        amount=Decimal(amount),
        cost_basis_usd=Decimal(cost_basis),
        acquisition_date=acquisition_date,
        source=source,
        tx_hash=tx_hash,
    )
    if remaining is not None:
        repo.update_remaining(lot_id, Decimal(remaining))
    return lot_id


# ---------------------------------------------------------------------------
# Test: Simple trace - exchange purchase -> hold
# ---------------------------------------------------------------------------

class TestSimpleExchangePurchase:
    def test_single_lot_traced(self, db):
        """An ETH purchase on Coinbase should produce a single-step trail."""
        _add_wallet(db, "0xuser1")
        _add_transaction(
            db,
            tx_hash="0xbuy1",
            tx_type="swap",
            protocol="Coinbase",
            raw_data={"to_address": "0xuser1"},
        )
        _add_lot(
            db,
            token="ETH",
            amount="2.0",
            cost_basis="4000",
            source="swap",
            tx_hash="0xbuy1",
        )

        report = trace_holdings(db)

        assert len(report.holdings) == 1
        h = report.holdings[0]
        assert h.token == "ETH"
        assert h.current_amount == Decimal("2.0")
        assert h.current_value_usd == Decimal("4000")
        assert h.acquisition_method == "swap"
        assert len(h.funding_trail) == 1
        assert h.funding_trail[0].source == "Coinbase"
        assert h.funding_trail[0].action == "swapped"

    def test_monetary_values_are_decimal(self, db):
        """All monetary values must be Decimal, never float."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xbuy1", protocol="Coinbase")
        _add_lot(db, token="ETH", amount="1.5", cost_basis="3000", tx_hash="0xbuy1")

        report = trace_holdings(db)

        h = report.holdings[0]
        assert isinstance(h.current_amount, Decimal)
        assert isinstance(h.current_value_usd, Decimal)
        assert isinstance(h.original_acquisition_cost, Decimal)
        assert isinstance(report.total_portfolio_value, Decimal)
        assert isinstance(report.total_acquisition_cost, Decimal)

        for step in h.funding_trail:
            assert isinstance(step.amount, Decimal)
            assert isinstance(step.value_usd, Decimal)


# ---------------------------------------------------------------------------
# Test: Multi-step - exchange purchase -> bridge -> swap -> hold
# ---------------------------------------------------------------------------

class TestMultiStepTrace:
    def test_multi_transaction_chain(self, db):
        """Holdings acquired through bridge + swap should show multi-step trail."""
        _add_wallet(db, "0xuser1")

        # Step 1: purchase on exchange
        _add_transaction(
            db,
            tx_hash="0xpurchase",
            timestamp="2025-01-01T10:00:00+00:00",
            tx_type="swap",
            protocol="Coinbase",
            raw_data={"to_address": "0xuser1", "prev_tx_hash": None},
        )

        # Step 2: bridge
        _add_transaction(
            db,
            tx_hash="0xbridge",
            timestamp="2025-01-05T10:00:00+00:00",
            tx_type="bridge",
            protocol="Arbitrum Bridge",
            raw_data={"to_address": "0xuser1", "prev_tx_hash": "0xpurchase"},
        )

        # Step 3: swap on DEX (the lot's tx)
        _add_transaction(
            db,
            tx_hash="0xswap",
            timestamp="2025-01-10T10:00:00+00:00",
            tx_type="swap",
            protocol="Uniswap V3",
            raw_data={"to_address": "0xuser1", "prev_tx_hash": "0xbridge"},
        )

        _add_lot(
            db,
            token="WETH",
            amount="1.0",
            cost_basis="2500",
            acquisition_date="2025-01-10T10:00:00+00:00",
            source="swap",
            tx_hash="0xswap",
        )

        report = trace_holdings(db)

        assert len(report.holdings) == 1
        h = report.holdings[0]
        assert h.token == "WETH"

        # Trail should have 3 steps (traced backward from swap -> bridge -> purchase)
        assert len(h.funding_trail) == 3
        # Chronological order: purchase first
        assert h.funding_trail[0].source == "Coinbase"
        assert h.funding_trail[1].source == "Arbitrum Bridge"
        assert h.funding_trail[2].source == "Uniswap V3"


# ---------------------------------------------------------------------------
# Test: Staking reward origin
# ---------------------------------------------------------------------------

class TestStakingRewardOrigin:
    def test_staking_reward_classified(self, db):
        """Staking rewards should be classified as staking_reward acquisition method."""
        _add_wallet(db, "0xstaker")
        _add_transaction(
            db,
            tx_hash="0xreward1",
            tx_type="reward",
            protocol="Lido Staking",
            raw_data={"to_address": "0xstaker"},
        )
        _add_lot(
            db,
            token="stETH",
            amount="0.5",
            cost_basis="1250",
            source="reward",
            tx_hash="0xreward1",
        )

        report = trace_holdings(db)

        h = report.holdings[0]
        assert h.acquisition_method == "staking_reward"
        assert h.funding_trail[0].action == "received_staking_reward"
        assert h.funding_trail[0].source == "Lido Staking"


# ---------------------------------------------------------------------------
# Test: Airdrop origin
# ---------------------------------------------------------------------------

class TestAirdropOrigin:
    def test_airdrop_classified(self, db):
        """Airdrops should be classified as airdrop acquisition method."""
        _add_wallet(db, "0xhodler")
        _add_transaction(
            db,
            tx_hash="0xairdrop1",
            tx_type="airdrop",
            protocol="Uniswap Governance",
            raw_data={"to_address": "0xhodler"},
        )
        _add_lot(
            db,
            token="UNI",
            amount="400",
            cost_basis="2000",
            source="airdrop",
            tx_hash="0xairdrop1",
        )

        report = trace_holdings(db)

        h = report.holdings[0]
        assert h.acquisition_method == "airdrop"
        assert h.token == "UNI"
        assert h.current_amount == Decimal("400")
        assert h.funding_trail[0].action == "airdrop"


# ---------------------------------------------------------------------------
# Test: Multiple holdings with different origins
# ---------------------------------------------------------------------------

class TestMultipleHoldings:
    def test_mixed_origins(self, db):
        """Report should handle multiple holdings with different acquisition methods."""
        _add_wallet(db, "0xuser1")

        # ETH from exchange purchase
        _add_transaction(
            db, tx_hash="0xbuy_eth", tx_type="swap", protocol="Coinbase",
            raw_data={"to_address": "0xuser1"},
        )
        _add_lot(
            db, token="ETH", amount="2.0", cost_basis="4000",
            source="swap", tx_hash="0xbuy_eth",
        )

        # stETH from staking
        _add_transaction(
            db, tx_hash="0xstake1", tx_type="reward", protocol="Lido",
            raw_data={"to_address": "0xuser1"},
        )
        _add_lot(
            db, token="stETH", amount="0.1", cost_basis="250",
            source="reward", tx_hash="0xstake1",
        )

        # UNI from airdrop
        _add_transaction(
            db, tx_hash="0xdrop1", tx_type="airdrop", protocol="Uniswap",
            raw_data={"to_address": "0xuser1"},
        )
        _add_lot(
            db, token="UNI", amount="400", cost_basis="1600",
            source="airdrop", tx_hash="0xdrop1",
        )

        report = trace_holdings(db)

        assert len(report.holdings) == 3
        tokens = {h.token for h in report.holdings}
        assert tokens == {"ETH", "stETH", "UNI"}

        methods = {h.token: h.acquisition_method for h in report.holdings}
        assert methods["ETH"] == "swap"
        assert methods["stETH"] == "staking_reward"
        assert methods["UNI"] == "airdrop"

        # Totals
        assert report.total_portfolio_value == Decimal("4000") + Decimal("250") + Decimal("1600")
        assert report.total_acquisition_cost == Decimal("4000") + Decimal("250") + Decimal("1600")

    def test_wallet_addresses_reported(self, db):
        """Report should list all covered wallet addresses."""
        _add_wallet(db, "0xwallet1")
        _add_wallet(db, "0xwallet2")
        _add_transaction(db, tx_hash="0xtx1")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1")

        report = trace_holdings(db)

        assert "0xwallet1" in report.wallet_addresses
        assert "0xwallet2" in report.wallet_addresses


# ---------------------------------------------------------------------------
# Test: CSV generation
# ---------------------------------------------------------------------------

class TestCSVGeneration:
    def test_csv_header_and_rows(self, db):
        """CSV output should have correct headers and data rows."""
        _add_wallet(db, "0xuser1")
        _add_transaction(
            db, tx_hash="0xbuy1", tx_type="swap", protocol="Coinbase",
            raw_data={"to_address": "0xuser1"},
        )
        _add_lot(
            db, token="ETH", amount="1.5", cost_basis="3000",
            source="swap", tx_hash="0xbuy1",
        )

        report = trace_holdings(db)
        csv_data = generate_source_of_funds_csv(report)

        lines = csv_data.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row

        header = lines[0]
        assert "Token" in header
        assert "Amount" in header
        assert "Current Value (USD)" in header
        assert "Acquisition Method" in header
        assert "Wallet Address" in header

        data_row = lines[1]
        assert "ETH" in data_row
        assert "1.5" in data_row

    def test_csv_multiple_holdings(self, db):
        """CSV should have one row per holding."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1", protocol="Coinbase")
        _add_transaction(db, tx_hash="0xtx2", protocol="Lido")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1", source="swap")
        _add_lot(db, token="stETH", amount="0.5", cost_basis="1000", tx_hash="0xtx2", source="reward")

        report = trace_holdings(db)
        csv_data = generate_source_of_funds_csv(report)

        lines = csv_data.strip().split("\n")
        assert len(lines) == 3  # header + 2 data rows

    def test_csv_decimal_precision(self, db):
        """CSV values should preserve Decimal precision (not float rounding)."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1")
        _add_lot(
            db, token="ETH", amount="0.123456789", cost_basis="246.913578",
            tx_hash="0xtx1",
        )

        report = trace_holdings(db)
        csv_data = generate_source_of_funds_csv(report)

        assert "0.123456789" in csv_data
        assert "246.913578" in csv_data


# ---------------------------------------------------------------------------
# Test: Text report generation
# ---------------------------------------------------------------------------

class TestTextReportGeneration:
    def test_text_contains_header(self, db):
        """Text report should contain the SOURCE OF FUNDS REPORT header."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1", protocol="Coinbase")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1")

        report = trace_holdings(db)
        text = generate_source_of_funds_text(report)

        assert "SOURCE OF FUNDS REPORT" in text

    def test_text_contains_holdings(self, db):
        """Text report should list each holding with details."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1", protocol="Coinbase")
        _add_lot(db, token="BTC", amount="0.5", cost_basis="25000", tx_hash="0xtx1")

        report = trace_holdings(db)
        text = generate_source_of_funds_text(report)

        assert "BTC" in text
        assert "HOLDING 1:" in text
        assert "$25000" in text

    def test_text_contains_methodology(self, db):
        """Text report should include methodology section."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1")

        report = trace_holdings(db)
        text = generate_source_of_funds_text(report)

        assert "METHODOLOGY" in text
        assert "on-chain" in text

    def test_text_contains_summary(self, db):
        """Text report should include a summary section."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1")

        report = trace_holdings(db)
        text = generate_source_of_funds_text(report)

        assert "SUMMARY" in text
        assert "Total Portfolio Value" in text
        assert "Total Acquisition Cost" in text

    def test_text_wallet_addresses_listed(self, db):
        """Text report should list all wallet addresses."""
        _add_wallet(db, "0xmywallet")
        _add_transaction(db, tx_hash="0xtx1")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1")

        report = trace_holdings(db)
        text = generate_source_of_funds_text(report)

        assert "0xmywallet" in text

    def test_text_trail_steps(self, db):
        """Text report should show transaction trail steps."""
        _add_wallet(db, "0xuser1")
        _add_transaction(
            db, tx_hash="0xbuy1", tx_type="swap", protocol="Coinbase",
            raw_data={"to_address": "0xuser1"},
        )
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xbuy1")

        report = trace_holdings(db)
        text = generate_source_of_funds_text(report)

        assert "Transaction Trail:" in text
        assert "Step 1:" in text
        assert "Coinbase" in text


# ---------------------------------------------------------------------------
# Test: Empty holdings (all sold)
# ---------------------------------------------------------------------------

class TestEmptyHoldings:
    def test_all_lots_consumed(self, db):
        """If all lots have remaining=0, report should have no holdings."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1")
        _add_lot(
            db, token="ETH", amount="1.0", cost_basis="2000",
            remaining="0", tx_hash="0xtx1",
        )

        report = trace_holdings(db)

        assert len(report.holdings) == 0
        assert report.total_portfolio_value == Decimal("0")
        assert report.total_acquisition_cost == Decimal("0")

    def test_no_lots_at_all(self, db):
        """If no tax lots exist, report should be empty."""
        _add_wallet(db, "0xuser1")

        report = trace_holdings(db)

        assert len(report.holdings) == 0
        assert report.wallet_addresses == ["0xuser1"]

    def test_empty_csv(self, db):
        """CSV for empty holdings should still have a header."""
        _add_wallet(db, "0xuser1")
        report = trace_holdings(db)
        csv_data = generate_source_of_funds_csv(report)

        lines = csv_data.strip().split("\n")
        assert len(lines) == 1  # header only
        assert "Token" in lines[0]

    def test_empty_text(self, db):
        """Text report for empty holdings should still be valid."""
        _add_wallet(db, "0xuser1")
        report = trace_holdings(db)
        text = generate_source_of_funds_text(report)

        assert "SOURCE OF FUNDS REPORT" in text
        assert "Total holdings traced: 0" in text


# ---------------------------------------------------------------------------
# Test: Wallet and token filters
# ---------------------------------------------------------------------------

class TestFilters:
    def test_token_filter(self, db):
        """Token filter should only include specified tokens."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1")
        _add_transaction(db, tx_hash="0xtx2")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1")
        _add_lot(db, token="BTC", amount="0.5", cost_basis="25000", tx_hash="0xtx2")

        report = trace_holdings(db, token_filter=["ETH"])

        assert len(report.holdings) == 1
        assert report.holdings[0].token == "ETH"

    def test_wallet_filter(self, db):
        """Wallet filter should restrict which wallets appear in the report."""
        _add_wallet(db, "0xwallet1")
        _add_wallet(db, "0xwallet2")
        _add_transaction(db, tx_hash="0xtx1")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1")

        report = trace_holdings(db, wallet_filter=["0xwallet1"])

        assert "0xwallet1" in report.wallet_addresses
        assert "0xwallet2" not in report.wallet_addresses


# ---------------------------------------------------------------------------
# Test: Partial remaining (partially sold lots)
# ---------------------------------------------------------------------------

class TestPartialRemaining:
    def test_proportional_cost_for_partial_lot(self, db):
        """If half a lot is sold, remaining cost should be proportional."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1")
        _add_lot(
            db, token="ETH", amount="2.0", cost_basis="4000",
            remaining="1.0", tx_hash="0xtx1",
        )

        report = trace_holdings(db)

        assert len(report.holdings) == 1
        h = report.holdings[0]
        assert h.current_amount == Decimal("1.0")
        # Proportional: 1.0/2.0 * 4000 = 2000
        assert h.current_value_usd == Decimal("2000")
        assert h.original_acquisition_cost == Decimal("2000")


# ---------------------------------------------------------------------------
# Test: Data model as_dict serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_report_as_dict(self, db):
        """as_dict() should produce a JSON-serializable dict with string Decimals."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1", protocol="Coinbase")
        _add_lot(db, token="ETH", amount="1.5", cost_basis="3000", tx_hash="0xtx1")

        report = trace_holdings(db)
        d = report.as_dict()

        # Should be JSON-serializable (all Decimals converted to strings)
        json_str = json.dumps(d)
        assert '"3000"' in json_str or '"3000.0"' in json_str or '"3000"' in json_str

        assert isinstance(d["total_portfolio_value"], str)
        assert isinstance(d["total_acquisition_cost"], str)
        assert isinstance(d["holdings"][0]["current_amount"], str)

    def test_holding_as_dict(self, db):
        """HoldingOrigin.as_dict() should include funding trail."""
        _add_wallet(db, "0xuser1")
        _add_transaction(db, tx_hash="0xtx1", protocol="Coinbase")
        _add_lot(db, token="ETH", amount="1", cost_basis="2000", tx_hash="0xtx1")

        report = trace_holdings(db)
        h_dict = report.holdings[0].as_dict()

        assert "funding_trail" in h_dict
        assert isinstance(h_dict["funding_trail"], list)
        assert h_dict["token"] == "ETH"
        assert h_dict["acquisition_method"] == "swap"
