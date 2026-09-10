"""
Tests for Sprint 4.5: 1099-DA Reconciliation.

Covers:
  - CSV parsing for Coinbase, Kraken, Binance formats
  - Auto-format detection
  - Generic CSV with column mapping
  - Exact and fuzzy matching
  - Unmatched entries on both sides
  - Cost basis and proceeds discrepancy detection
  - Reconciliation summary statistics
  - Real-world-like scenario (10+ entries, mix of matches and mismatches)
  - Report generation (CSV + text summary)

CRITICAL: All monetary values use Decimal - NEVER float.
"""
from __future__ import annotations

import csv
import io
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.importers.form_1099da import (
    Form1099DAEntry,
    detect_format,
    parse_1099da_auto,
    parse_binance_1099da,
    parse_coinbase_1099da,
    parse_generic_1099da,
    parse_kraken_1099da,
)
from src.calculator.lots import Disposal, LotConsumption
from src.tax.us.reconciliation import (
    DiscrepancyType,
    MatchConfidence,
    ReconciliationResult,
    reconcile,
)
from src.tax.us.reconciliation_report import (
    generate_reconciliation_csv,
    generate_reconciliation_summary,
)


# ---------------------------------------------------------------------------
# Fixtures: temp CSV file helpers
# ---------------------------------------------------------------------------

def _write_csv(rows: list[list[str]], headers: list[str]) -> str:
    """Write CSV to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
    writer = csv.writer(tmp)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    tmp.close()
    return tmp.name


def _make_disposal(
    token: str,
    dt: datetime,
    proceeds: Decimal,
    cost_basis: Decimal,
    gain_loss: Decimal | None = None,
    method: str = "FIFO",
    tx_hash: str = "0xabc",
) -> Disposal:
    """Create a Disposal object for testing."""
    if gain_loss is None:
        gain_loss = proceeds - cost_basis
    return Disposal(
        date=dt,
        token=token,
        amount=Decimal("1"),
        proceeds_usd=proceeds,
        cost_basis_usd=cost_basis,
        gain_loss_usd=gain_loss,
        holding_period="short-term",
        method=method,
        lots_consumed=[],
        tx_hash=tx_hash,
    )


# ===========================================================================
# Test: CSV parsing - Coinbase format
# ===========================================================================

class TestCoinbaseParsing:
    def test_basic_coinbase_csv(self):
        headers = [
            "Asset Name", "Date Acquired", "Date Sold or Disposed",
            "Proceeds", "Cost Basis", "Gain or Loss", "Covered",
        ]
        rows = [
            ["BTC", "2024-01-15", "2025-06-20", "$5,000.00", "$3,000.00", "$2,000.00", "No"],
            ["ETH", "VARIOUS", "2025-07-10", "$2,500.50", "", "", "Yes"],
            ["SOL", "2024-03-01", "2025-08-15", "$800.00", "$600.00", "$200.00", "No"],
        ]
        path = _write_csv(rows, headers)

        entries = parse_coinbase_1099da(path)
        assert len(entries) == 3

        # First entry
        assert entries[0].asset == "BTC"
        assert entries[0].date_acquired == date(2024, 1, 15)
        assert entries[0].date_sold == date(2025, 6, 20)
        assert entries[0].proceeds == Decimal("5000.00")
        assert entries[0].cost_basis == Decimal("3000.00")
        assert entries[0].gain_loss == Decimal("2000.00")
        assert entries[0].broker_name == "Coinbase"
        assert entries[0].is_covered is False

        # Second entry - VARIOUS date acquired, no cost basis
        assert entries[1].asset == "ETH"
        assert entries[1].date_acquired is None  # VARIOUS → None
        assert entries[1].date_sold == date(2025, 7, 10)
        assert entries[1].proceeds == Decimal("2500.50")
        assert entries[1].cost_basis is None
        assert entries[1].is_covered is True

        Path(path).unlink()

    def test_empty_rows_skipped(self):
        headers = [
            "Asset Name", "Date Acquired", "Date Sold or Disposed",
            "Proceeds", "Cost Basis", "Gain or Loss", "Covered",
        ]
        rows = [
            ["BTC", "2024-01-15", "2025-06-20", "$1,000.00", "$500.00", "$500.00", "No"],
            ["", "", "", "", "", "", ""],  # empty row
        ]
        path = _write_csv(rows, headers)
        entries = parse_coinbase_1099da(path)
        assert len(entries) == 1
        Path(path).unlink()


# ===========================================================================
# Test: CSV parsing - Kraken format
# ===========================================================================

class TestKrakenParsing:
    def test_basic_kraken_csv(self):
        headers = [
            "Asset", "Date Acquired", "Date of Sale",
            "Gross Proceeds", "Cost Basis", "Gain/Loss",
        ]
        rows = [
            ["BTC", "01/15/2024", "06/20/2025", "5000.00", "3000.00", "2000.00"],
            ["ETH", "VARIOUS", "07/10/2025", "2500.50", "", ""],
        ]
        path = _write_csv(rows, headers)

        entries = parse_kraken_1099da(path)
        assert len(entries) == 2

        assert entries[0].asset == "BTC"
        assert entries[0].date_sold == date(2025, 6, 20)
        assert entries[0].proceeds == Decimal("5000.00")
        assert entries[0].broker_name == "Kraken"

        assert entries[1].date_acquired is None
        assert entries[1].proceeds == Decimal("2500.50")

        Path(path).unlink()


# ===========================================================================
# Test: CSV parsing - Binance format
# ===========================================================================

class TestBinanceParsing:
    def test_basic_binance_csv(self):
        headers = [
            "Asset", "Date Acquired", "Date Sold",
            "Gross Proceeds", "Cost Basis", "Gain/Loss", "Covered",
        ]
        rows = [
            ["BTC", "2024-01-15", "2025-06-20", "5000.00", "3000.00", "2000.00", "No"],
            ["DOGE", "2024-02-01", "2025-08-01", "100.00", "150.00", "-50.00", "No"],
        ]
        path = _write_csv(rows, headers)

        entries = parse_binance_1099da(path)
        assert len(entries) == 2

        assert entries[0].asset == "BTC"
        assert entries[0].broker_name == "Binance.US"

        assert entries[1].asset == "DOGE"
        assert entries[1].gain_loss == Decimal("-50.00")

        Path(path).unlink()


# ===========================================================================
# Test: Auto-detect format
# ===========================================================================

class TestAutoDetect:
    def test_detect_coinbase(self):
        headers = {"Asset Name", "Date Acquired", "Date Sold or Disposed", "Proceeds", "Cost Basis"}
        assert detect_format(headers) == "coinbase"

    def test_detect_kraken(self):
        headers = {"Asset", "Date Acquired", "Date of Sale", "Gross Proceeds"}
        assert detect_format(headers) == "kraken"

    def test_detect_binance(self):
        headers = {"Asset", "Date Acquired", "Date Sold", "Gross Proceeds"}
        assert detect_format(headers) == "binance"

    def test_detect_generic(self):
        headers = {"Symbol", "Sold On", "Amount Received"}
        assert detect_format(headers) == "generic"

    def test_auto_parse_coinbase(self):
        headers = [
            "Asset Name", "Date Acquired", "Date Sold or Disposed",
            "Proceeds", "Cost Basis", "Gain or Loss", "Covered",
        ]
        rows = [
            ["BTC", "2024-01-15", "2025-06-20", "5000.00", "3000.00", "2000.00", "No"],
        ]
        path = _write_csv(rows, headers)
        entries = parse_1099da_auto(path)
        assert len(entries) == 1
        assert entries[0].broker_name == "Coinbase"
        Path(path).unlink()


# ===========================================================================
# Test: Generic CSV with column mapping
# ===========================================================================

class TestGenericParsing:
    def test_custom_mapping(self):
        headers = ["Token", "Buy Date", "Sell Date", "Sale Amount", "Purchase Price"]
        rows = [
            ["BTC", "2024-01-15", "2025-06-20", "5000.00", "3000.00"],
            ["ETH", "2024-03-01", "2025-07-01", "1200.00", "800.00"],
        ]
        path = _write_csv(rows, headers)

        mapping = {
            "asset": "Token",
            "date_acquired": "Buy Date",
            "date_sold": "Sell Date",
            "proceeds": "Sale Amount",
            "cost_basis": "Purchase Price",
            "broker_name": "CustomExchange",
        }

        entries = parse_generic_1099da(path, mapping)
        assert len(entries) == 2
        assert entries[0].asset == "BTC"
        assert entries[0].proceeds == Decimal("5000.00")
        assert entries[0].cost_basis == Decimal("3000.00")
        assert entries[0].broker_name == "CustomExchange"

        Path(path).unlink()

    def test_missing_required_mapping(self):
        headers = ["Token", "Sell Date", "Sale Amount"]
        rows = [["BTC", "2025-06-20", "5000.00"]]
        path = _write_csv(rows, headers)

        # Missing "asset" key
        mapping = {
            "date_sold": "Sell Date",
            "proceeds": "Sale Amount",
        }

        with pytest.raises(ValueError, match="missing required keys"):
            parse_generic_1099da(path, mapping)

        Path(path).unlink()


# ===========================================================================
# Test: Exact match scenario
# ===========================================================================

class TestExactMatch:
    def test_exact_match(self):
        """1099-DA entry matches our disposal exactly (same date, asset, proceeds)."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC",
                date_acquired=date(2024, 1, 15),
                date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"),
                cost_basis=Decimal("3000.00"),
                gain_loss=Decimal("2000.00"),
                broker_name="Coinbase",
                is_covered=False,
                raw_row={},
            ),
        ]

        our_disposals = [
            _make_disposal(
                token="BTC",
                dt=datetime(2025, 6, 20, 14, 30, tzinfo=timezone.utc),
                proceeds=Decimal("5000.00"),
                cost_basis=Decimal("3000.00"),
            ),
        ]

        result = reconcile(form_entries, our_disposals)

        assert len(result.matched) == 1
        assert result.matched[0].confidence == MatchConfidence.EXACT
        assert len(result.unmatched_1099) == 0
        assert len(result.unmatched_ours) == 0
        assert result.match_rate == Decimal("100.00")

    def test_exact_match_proceeds_within_2pct(self):
        """Proceeds within 2% should still be EXACT match."""
        form_entries = [
            Form1099DAEntry(
                asset="ETH",
                date_acquired=None,
                date_sold=date(2025, 7, 10),
                proceeds=Decimal("2500.00"),
                cost_basis=None,
                gain_loss=None,
                broker_name="Kraken",
                is_covered=False,
                raw_row={},
            ),
        ]

        our_disposals = [
            _make_disposal(
                token="ETH",
                dt=datetime(2025, 7, 10, 10, 0, tzinfo=timezone.utc),
                proceeds=Decimal("2480.00"),  # within 2%
                cost_basis=Decimal("1500.00"),
            ),
        ]

        result = reconcile(form_entries, our_disposals)
        assert len(result.matched) == 1
        assert result.matched[0].confidence == MatchConfidence.EXACT


# ===========================================================================
# Test: Fuzzy match (date off by 1 day)
# ===========================================================================

class TestFuzzyMatch:
    def test_fuzzy_match_date_off_by_one(self):
        """Date differs by 1 day → FUZZY match."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC",
                date_acquired=date(2024, 1, 15),
                date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"),
                cost_basis=Decimal("3000.00"),
                gain_loss=Decimal("2000.00"),
                broker_name="Coinbase",
                is_covered=False,
                raw_row={},
            ),
        ]

        our_disposals = [
            _make_disposal(
                token="BTC",
                dt=datetime(2025, 6, 21, 0, 0, tzinfo=timezone.utc),  # +1 day
                proceeds=Decimal("5000.00"),
                cost_basis=Decimal("3000.00"),
            ),
        ]

        result = reconcile(form_entries, our_disposals)
        assert len(result.matched) == 1
        assert result.matched[0].confidence == MatchConfidence.FUZZY

    def test_fuzzy_match_proceeds_within_5pct(self):
        """Proceeds differ by ~4% (between 2% and 5%) → FUZZY match."""
        form_entries = [
            Form1099DAEntry(
                asset="SOL",
                date_acquired=None,
                date_sold=date(2025, 8, 15),
                proceeds=Decimal("1000.00"),
                cost_basis=None,
                gain_loss=None,
                broker_name="Binance.US",
                is_covered=False,
                raw_row={},
            ),
        ]

        our_disposals = [
            _make_disposal(
                token="SOL",
                dt=datetime(2025, 8, 15, 12, 0, tzinfo=timezone.utc),
                proceeds=Decimal("960.00"),  # 4% diff
                cost_basis=Decimal("500.00"),
            ),
        ]

        result = reconcile(form_entries, our_disposals)
        assert len(result.matched) == 1
        assert result.matched[0].confidence == MatchConfidence.FUZZY


# ===========================================================================
# Test: Unmatched on both sides
# ===========================================================================

class TestUnmatched:
    def test_unmatched_1099_entry(self):
        """1099-DA entry with no matching disposal → MISSING_IMPORT."""
        form_entries = [
            Form1099DAEntry(
                asset="AVAX",
                date_acquired=None,
                date_sold=date(2025, 9, 1),
                proceeds=Decimal("3000.00"),
                cost_basis=None,
                gain_loss=None,
                broker_name="Coinbase",
                is_covered=False,
                raw_row={},
            ),
        ]

        result = reconcile(form_entries, [])

        assert len(result.matched) == 0
        assert len(result.unmatched_1099) == 1
        assert result.unmatched_1099[0].asset == "AVAX"
        assert result.match_rate == Decimal("0.00")

        # Should have a MISSING_IMPORT discrepancy
        missing = [d for d in result.discrepancies if d.type == DiscrepancyType.MISSING_IMPORT]
        assert len(missing) == 1
        assert "Coinbase" in missing[0].guidance

    def test_unmatched_our_disposal(self):
        """Our disposal with no 1099-DA entry → DEFI_NOT_ON_1099."""
        our_disposals = [
            _make_disposal(
                token="UNI",
                dt=datetime(2025, 7, 15, 0, 0, tzinfo=timezone.utc),
                proceeds=Decimal("1500.00"),
                cost_basis=Decimal("800.00"),
            ),
        ]

        result = reconcile([], our_disposals)

        assert len(result.matched) == 0
        assert len(result.unmatched_ours) == 1
        assert result.match_rate == Decimal("100.00")  # no 1099 entries → 100% match

        # Should have a DEFI_NOT_ON_1099 discrepancy
        defi = [d for d in result.discrepancies if d.type == DiscrepancyType.DEFI_NOT_ON_1099]
        assert len(defi) == 1
        assert "Form 8949" in defi[0].guidance


# ===========================================================================
# Test: Cost basis discrepancy detection
# ===========================================================================

class TestCostBasisDiscrepancy:
    def test_cost_basis_mismatch(self):
        """Matched entry with different cost basis → COST_BASIS_DIFF discrepancy."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC",
                date_acquired=date(2024, 1, 15),
                date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"),
                cost_basis=Decimal("2500.00"),  # 1099-DA says $2500
                gain_loss=Decimal("2500.00"),
                broker_name="Coinbase",
                is_covered=False,
                raw_row={},
            ),
        ]

        our_disposals = [
            _make_disposal(
                token="BTC",
                dt=datetime(2025, 6, 20, 14, 30, tzinfo=timezone.utc),
                proceeds=Decimal("5000.00"),
                cost_basis=Decimal("3000.00"),  # we say $3000
            ),
        ]

        result = reconcile(form_entries, our_disposals)

        assert len(result.matched) == 1
        assert result.matched[0].confidence == MatchConfidence.EXACT

        # Should detect cost basis discrepancy
        cb_discs = [
            d for d in result.matched[0].discrepancies
            if d.type == DiscrepancyType.COST_BASIS_DIFF
        ]
        assert len(cb_discs) == 1
        assert cb_discs[0].form_value == Decimal("2500.00")
        assert cb_discs[0].our_value == Decimal("3000.00")
        assert "transfers between wallets" in cb_discs[0].guidance


# ===========================================================================
# Test: Reconciliation summary statistics
# ===========================================================================

class TestSummaryStatistics:
    def test_summary_totals(self):
        """Verify total proceeds and match rate calculations."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC", date_acquired=None, date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"), cost_basis=None, gain_loss=None,
                broker_name="Coinbase", is_covered=False, raw_row={},
            ),
            Form1099DAEntry(
                asset="ETH", date_acquired=None, date_sold=date(2025, 7, 10),
                proceeds=Decimal("2000.00"), cost_basis=None, gain_loss=None,
                broker_name="Coinbase", is_covered=False, raw_row={},
            ),
        ]

        our_disposals = [
            _make_disposal("BTC", datetime(2025, 6, 20, tzinfo=timezone.utc),
                           Decimal("5000.00"), Decimal("3000.00")),
        ]

        result = reconcile(form_entries, our_disposals)

        assert result.total_1099_proceeds == Decimal("7000.00")
        assert result.total_our_proceeds == Decimal("5000.00")
        assert result.match_rate == Decimal("50.00")  # 1 of 2 matched
        assert len(result.matched) == 1
        assert len(result.unmatched_1099) == 1

    def test_summary_text_contains_key_info(self):
        form_entries = [
            Form1099DAEntry(
                asset="BTC", date_acquired=None, date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"), cost_basis=None, gain_loss=None,
                broker_name="Coinbase", is_covered=False, raw_row={},
            ),
        ]
        result = reconcile(form_entries, [])
        assert "Reconciliation Summary" in result.summary_text
        assert "1099-DA entries" in result.summary_text


# ===========================================================================
# Test: Real-world-like scenario (10+ entries)
# ===========================================================================

class TestRealWorldScenario:
    def test_mixed_matches_and_mismatches(self):
        """
        Simulate real data: 12 1099-DA entries, 10 disposals.
        Mix of exact matches, fuzzy matches, unmatched on both sides,
        and cost basis discrepancies.
        """
        form_entries = [
            # 1. Exact match
            Form1099DAEntry(
                asset="BTC", date_acquired=date(2024, 1, 15), date_sold=date(2025, 3, 10),
                proceeds=Decimal("45000.00"), cost_basis=Decimal("30000.00"),
                gain_loss=Decimal("15000.00"), broker_name="Coinbase",
                is_covered=False, raw_row={},
            ),
            # 2. Exact match
            Form1099DAEntry(
                asset="ETH", date_acquired=date(2024, 2, 20), date_sold=date(2025, 4, 15),
                proceeds=Decimal("3200.00"), cost_basis=Decimal("2000.00"),
                gain_loss=Decimal("1200.00"), broker_name="Coinbase",
                is_covered=False, raw_row={},
            ),
            # 3. Fuzzy match (date off by 1 day)
            Form1099DAEntry(
                asset="SOL", date_acquired=date(2024, 3, 1), date_sold=date(2025, 5, 20),
                proceeds=Decimal("800.00"), cost_basis=Decimal("400.00"),
                gain_loss=Decimal("400.00"), broker_name="Kraken",
                is_covered=False, raw_row={},
            ),
            # 4. Fuzzy match (proceeds within 3%)
            Form1099DAEntry(
                asset="AVAX", date_acquired=date(2024, 4, 10), date_sold=date(2025, 6, 1),
                proceeds=Decimal("1000.00"), cost_basis=Decimal("700.00"),
                gain_loss=Decimal("300.00"), broker_name="Kraken",
                is_covered=False, raw_row={},
            ),
            # 5. Exact match with cost basis discrepancy
            Form1099DAEntry(
                asset="MATIC", date_acquired=date(2024, 5, 15), date_sold=date(2025, 7, 1),
                proceeds=Decimal("500.00"), cost_basis=Decimal("200.00"),
                gain_loss=Decimal("300.00"), broker_name="Coinbase",
                is_covered=False, raw_row={},
            ),
            # 6. Exact match
            Form1099DAEntry(
                asset="LINK", date_acquired=date(2024, 6, 1), date_sold=date(2025, 8, 15),
                proceeds=Decimal("2100.00"), cost_basis=Decimal("1500.00"),
                gain_loss=Decimal("600.00"), broker_name="Binance.US",
                is_covered=False, raw_row={},
            ),
            # 7. Unmatched - missing from our data
            Form1099DAEntry(
                asset="DOT", date_acquired=date(2024, 7, 1), date_sold=date(2025, 9, 1),
                proceeds=Decimal("1500.00"), cost_basis=Decimal("1200.00"),
                gain_loss=Decimal("300.00"), broker_name="Kraken",
                is_covered=False, raw_row={},
            ),
            # 8. Unmatched - missing from our data
            Form1099DAEntry(
                asset="ADA", date_acquired=date(2024, 8, 1), date_sold=date(2025, 10, 1),
                proceeds=Decimal("600.00"), cost_basis=Decimal("400.00"),
                gain_loss=Decimal("200.00"), broker_name="Binance.US",
                is_covered=False, raw_row={},
            ),
            # 9. Exact match
            Form1099DAEntry(
                asset="DOGE", date_acquired=date(2024, 9, 1), date_sold=date(2025, 6, 15),
                proceeds=Decimal("200.00"), cost_basis=Decimal("100.00"),
                gain_loss=Decimal("100.00"), broker_name="Coinbase",
                is_covered=False, raw_row={},
            ),
            # 10. Exact match with loss
            Form1099DAEntry(
                asset="SHIB", date_acquired=date(2024, 10, 1), date_sold=date(2025, 5, 1),
                proceeds=Decimal("50.00"), cost_basis=Decimal("150.00"),
                gain_loss=Decimal("-100.00"), broker_name="Coinbase",
                is_covered=False, raw_row={},
            ),
            # 11. Fuzzy match (both date and proceeds slightly off)
            Form1099DAEntry(
                asset="BTC", date_acquired=date(2024, 11, 1), date_sold=date(2025, 11, 15),
                proceeds=Decimal("52000.00"), cost_basis=Decimal("48000.00"),
                gain_loss=Decimal("4000.00"), broker_name="Kraken",
                is_covered=False, raw_row={},
            ),
            # 12. Exact match
            Form1099DAEntry(
                asset="ETH", date_acquired=date(2024, 12, 1), date_sold=date(2025, 12, 20),
                proceeds=Decimal("4000.00"), cost_basis=Decimal("3500.00"),
                gain_loss=Decimal("500.00"), broker_name="Coinbase",
                is_covered=False, raw_row={},
            ),
        ]

        our_disposals = [
            # Matches entry 1 exactly
            _make_disposal("BTC", datetime(2025, 3, 10, 14, 0, tzinfo=timezone.utc),
                           Decimal("45000.00"), Decimal("30000.00"), tx_hash="0x001"),
            # Matches entry 2 exactly
            _make_disposal("ETH", datetime(2025, 4, 15, 10, 0, tzinfo=timezone.utc),
                           Decimal("3200.00"), Decimal("2000.00"), tx_hash="0x002"),
            # Matches entry 3 fuzzy (date off by 1)
            _make_disposal("SOL", datetime(2025, 5, 21, 8, 0, tzinfo=timezone.utc),
                           Decimal("800.00"), Decimal("400.00"), tx_hash="0x003"),
            # Matches entry 4 fuzzy (proceeds within 3%)
            _make_disposal("AVAX", datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
                           Decimal("975.00"), Decimal("700.00"), tx_hash="0x004"),
            # Matches entry 5 but with different cost basis
            _make_disposal("MATIC", datetime(2025, 7, 1, 15, 0, tzinfo=timezone.utc),
                           Decimal("500.00"), Decimal("350.00"), tx_hash="0x005"),
            # Matches entry 6 exactly
            _make_disposal("LINK", datetime(2025, 8, 15, 9, 0, tzinfo=timezone.utc),
                           Decimal("2100.00"), Decimal("1500.00"), tx_hash="0x006"),
            # Matches entry 9 exactly
            _make_disposal("DOGE", datetime(2025, 6, 15, 11, 0, tzinfo=timezone.utc),
                           Decimal("200.00"), Decimal("100.00"), tx_hash="0x009"),
            # Matches entry 10 exactly
            _make_disposal("SHIB", datetime(2025, 5, 1, 16, 0, tzinfo=timezone.utc),
                           Decimal("50.00"), Decimal("150.00"), tx_hash="0x010"),
            # Matches entry 11 fuzzy
            _make_disposal("BTC", datetime(2025, 11, 16, 3, 0, tzinfo=timezone.utc),
                           Decimal("51000.00"), Decimal("48000.00"), tx_hash="0x011"),
            # Matches entry 12 exactly
            _make_disposal("ETH", datetime(2025, 12, 20, 20, 0, tzinfo=timezone.utc),
                           Decimal("4000.00"), Decimal("3500.00"), tx_hash="0x012"),
            # DeFi disposal - not on any 1099
            _make_disposal("UNI", datetime(2025, 8, 1, 0, 0, tzinfo=timezone.utc),
                           Decimal("750.00"), Decimal("300.00"), tx_hash="0xdefi1"),
            # Another DeFi disposal
            _make_disposal("AAVE", datetime(2025, 9, 15, 0, 0, tzinfo=timezone.utc),
                           Decimal("1200.00"), Decimal("900.00"), tx_hash="0xdefi2"),
        ]

        result = reconcile(form_entries, our_disposals)

        # 10 of 12 1099-DA entries should be matched
        assert len(result.matched) == 10

        # 2 unmatched on 1099 side (DOT, ADA)
        assert len(result.unmatched_1099) == 2
        unmatched_assets = {e.asset for e in result.unmatched_1099}
        assert "DOT" in unmatched_assets
        assert "ADA" in unmatched_assets

        # 2 unmatched on our side (UNI, AAVE - DeFi)
        assert len(result.unmatched_ours) == 2
        unmatched_our_tokens = {d.token for d in result.unmatched_ours}
        assert "UNI" in unmatched_our_tokens
        assert "AAVE" in unmatched_our_tokens

        # Match rate = 10/12 = 83.33%
        assert result.match_rate == Decimal("83.33")

        # Check confidence distribution
        exact_count = sum(1 for m in result.matched if m.confidence == MatchConfidence.EXACT)
        fuzzy_count = sum(1 for m in result.matched if m.confidence == MatchConfidence.FUZZY)
        assert exact_count >= 6  # at least 6 exact matches
        assert fuzzy_count >= 2  # at least 2 fuzzy matches

        # Check for cost basis discrepancy on MATIC
        matic_match = [m for m in result.matched if m.form_entry.asset == "MATIC"][0]
        cb_discs = [d for d in matic_match.discrepancies if d.type == DiscrepancyType.COST_BASIS_DIFF]
        assert len(cb_discs) == 1

        # Check discrepancy types
        disc_types = {d.type for d in result.discrepancies}
        assert DiscrepancyType.MISSING_IMPORT in disc_types
        assert DiscrepancyType.DEFI_NOT_ON_1099 in disc_types
        assert DiscrepancyType.COST_BASIS_DIFF in disc_types

        # Verify all Decimal precision
        assert isinstance(result.total_1099_proceeds, Decimal)
        assert isinstance(result.total_our_proceeds, Decimal)
        assert isinstance(result.match_rate, Decimal)


# ===========================================================================
# Test: Report generation
# ===========================================================================

class TestReportGeneration:
    def _make_result(self) -> ReconciliationResult:
        """Build a small result for report testing."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC", date_acquired=date(2024, 1, 15), date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"), cost_basis=Decimal("3000.00"),
                gain_loss=Decimal("2000.00"), broker_name="Coinbase",
                is_covered=False, raw_row={},
            ),
            Form1099DAEntry(
                asset="AVAX", date_acquired=None, date_sold=date(2025, 9, 1),
                proceeds=Decimal("1500.00"), cost_basis=None,
                gain_loss=None, broker_name="Kraken",
                is_covered=False, raw_row={},
            ),
        ]
        our_disposals = [
            _make_disposal("BTC", datetime(2025, 6, 20, 14, 0, tzinfo=timezone.utc),
                           Decimal("5000.00"), Decimal("3000.00")),
            _make_disposal("UNI", datetime(2025, 7, 15, 0, 0, tzinfo=timezone.utc),
                           Decimal("750.00"), Decimal("300.00")),
        ]
        return reconcile(form_entries, our_disposals)

    def test_csv_report_headers(self):
        result = self._make_result()
        csv_text = generate_reconciliation_csv(result)

        reader = csv.reader(io.StringIO(csv_text))
        headers = next(reader)
        assert "Status" in headers
        assert "Asset" in headers
        assert "1099-DA Proceeds" in headers
        assert "Our Proceeds" in headers
        assert "Guidance" in headers

    def test_csv_report_row_count(self):
        result = self._make_result()
        csv_text = generate_reconciliation_csv(result)

        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # 1 header + 1 matched + 1 unmatched_1099 + 1 unmatched_ours = 4
        assert len(rows) == 4

    def test_csv_report_contains_matched(self):
        result = self._make_result()
        csv_text = generate_reconciliation_csv(result)
        assert "Matched" in csv_text
        assert "BTC" in csv_text

    def test_csv_report_contains_unmatched(self):
        result = self._make_result()
        csv_text = generate_reconciliation_csv(result)
        assert "Missing Import" in csv_text
        assert "AVAX" in csv_text
        assert "DeFi" in csv_text
        assert "UNI" in csv_text

    def test_summary_report(self):
        result = self._make_result()
        summary = generate_reconciliation_summary(result)

        assert "Reconciliation Summary" in summary
        assert "Matched" in summary
        assert "BTC" in summary

    def test_summary_report_contains_discrepancy_guidance(self):
        # Build a result with a cost basis discrepancy
        form_entries = [
            Form1099DAEntry(
                asset="BTC", date_acquired=date(2024, 1, 15), date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"), cost_basis=Decimal("2000.00"),
                gain_loss=Decimal("3000.00"), broker_name="Coinbase",
                is_covered=False, raw_row={},
            ),
        ]
        our_disposals = [
            _make_disposal("BTC", datetime(2025, 6, 20, 14, 0, tzinfo=timezone.utc),
                           Decimal("5000.00"), Decimal("3500.00")),
        ]
        result = reconcile(form_entries, our_disposals)
        summary = generate_reconciliation_summary(result)

        assert "Guidance:" in summary
        assert "transfers between wallets" in summary


# ===========================================================================
# Test: Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_empty_inputs(self):
        """Both inputs empty → clean result."""
        result = reconcile([], [])
        assert len(result.matched) == 0
        assert len(result.unmatched_1099) == 0
        assert len(result.unmatched_ours) == 0
        assert result.match_rate == Decimal("100.00")
        assert result.total_1099_proceeds == Decimal("0")
        assert result.total_our_proceeds == Decimal("0")

    def test_no_match_different_assets(self):
        """Same date/proceeds but different asset → no match."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC", date_acquired=None, date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"), cost_basis=None, gain_loss=None,
                broker_name="Coinbase", is_covered=False, raw_row={},
            ),
        ]
        our_disposals = [
            _make_disposal("ETH", datetime(2025, 6, 20, 0, 0, tzinfo=timezone.utc),
                           Decimal("5000.00"), Decimal("3000.00")),
        ]
        result = reconcile(form_entries, our_disposals)
        assert len(result.matched) == 0
        assert len(result.unmatched_1099) == 1
        assert len(result.unmatched_ours) == 1

    def test_no_match_date_too_far(self):
        """Date differs by 3 days → no match (tolerance is ±1 day)."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC", date_acquired=None, date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"), cost_basis=None, gain_loss=None,
                broker_name="Coinbase", is_covered=False, raw_row={},
            ),
        ]
        our_disposals = [
            _make_disposal("BTC", datetime(2025, 6, 23, 0, 0, tzinfo=timezone.utc),
                           Decimal("5000.00"), Decimal("3000.00")),
        ]
        result = reconcile(form_entries, our_disposals)
        assert len(result.matched) == 0

    def test_no_match_proceeds_too_far(self):
        """Proceeds differ by 10% → no match (tolerance is 5%)."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC", date_acquired=None, date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.00"), cost_basis=None, gain_loss=None,
                broker_name="Coinbase", is_covered=False, raw_row={},
            ),
        ]
        our_disposals = [
            _make_disposal("BTC", datetime(2025, 6, 20, 0, 0, tzinfo=timezone.utc),
                           Decimal("4400.00"), Decimal("3000.00")),  # 12% diff
        ]
        result = reconcile(form_entries, our_disposals)
        assert len(result.matched) == 0

    def test_decimal_precision_preserved(self):
        """Verify Decimal types throughout the result."""
        form_entries = [
            Form1099DAEntry(
                asset="BTC", date_acquired=None, date_sold=date(2025, 6, 20),
                proceeds=Decimal("5000.123456"), cost_basis=Decimal("3000.654321"),
                gain_loss=None, broker_name="Coinbase", is_covered=False, raw_row={},
            ),
        ]
        our_disposals = [
            _make_disposal("BTC", datetime(2025, 6, 20, 0, 0, tzinfo=timezone.utc),
                           Decimal("5000.123456"), Decimal("3100.00")),
        ]
        result = reconcile(form_entries, our_disposals)

        assert isinstance(result.total_1099_proceeds, Decimal)
        assert isinstance(result.total_our_proceeds, Decimal)
        assert isinstance(result.match_rate, Decimal)

        if result.matched:
            for m in result.matched:
                assert isinstance(m.form_entry.proceeds, Decimal)
                assert isinstance(m.our_disposal.proceeds_usd, Decimal)

    def test_form1099da_type_enforcement(self):
        """Form1099DAEntry rejects non-Decimal proceeds."""
        with pytest.raises(TypeError, match="proceeds must be Decimal"):
            Form1099DAEntry(
                asset="BTC", date_acquired=None, date_sold=date(2025, 6, 20),
                proceeds=5000.0,  # type: ignore - testing enforcement
                cost_basis=None, gain_loss=None,
                broker_name="Coinbase", is_covered=False, raw_row={},
            )
