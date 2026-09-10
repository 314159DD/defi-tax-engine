"""
Report generation tests.

Covers:
- Form 8949 output format (Part I short-term, Part II long-term)
- Schedule D summary totals matching Form 8949 line items
- TurboTax CSV export format
- Tax loss harvesting suggestions sorted by savings amount
- All Decimal, no float
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest

from src.reports.form_8949 import Form8949Generator, Form8949Line, _box_code
from src.reports.schedule_d import ScheduleDGenerator, ScheduleDSummary
from src.reports.csv_export import TurboTaxExporter
from src.reports.harvest import HarvestAnalyzer, HarvestSuggestion
from src.storage.database import Database, DisposalRepository, TaxLotRepository


# ── Helpers ────────────────────────────────────────────────────────────────────

def _seed_disposals(db: Database) -> None:
    """Insert sample disposals for 2025 tests."""
    repo = DisposalRepository(db)
    # Short-term gain
    repo.insert(
        token="ETH",
        amount=Decimal("1"),
        proceeds_usd=Decimal("3000"),
        cost_basis_usd=Decimal("2000"),
        gain_loss_usd=Decimal("1000"),
        holding_period="short",
        method="FIFO",
        disposal_date="2025-06-01T12:00:00",
        tx_hash="0xshort1",
    )
    # Long-term gain
    repo.insert(
        token="BTC",
        amount=Decimal("0.5"),
        proceeds_usd=Decimal("25000"),
        cost_basis_usd=Decimal("15000"),
        gain_loss_usd=Decimal("10000"),
        holding_period="long",
        method="FIFO",
        disposal_date="2025-07-01T12:00:00",
        tx_hash="0xlong1",
    )
    # Short-term loss
    repo.insert(
        token="SOL",
        amount=Decimal("10"),
        proceeds_usd=Decimal("500"),
        cost_basis_usd=Decimal("800"),
        gain_loss_usd=Decimal("-300"),
        holding_period="short",
        method="FIFO",
        disposal_date="2025-08-01T12:00:00",
        tx_hash="0xshort2",
    )


def _seed_lots(db: Database) -> None:
    """Insert open tax lots for harvest tests."""
    repo = TaxLotRepository(db)
    # ETH lot at a loss (bought at $3000, currently $2000)
    repo.insert(
        token="ETH",
        amount=Decimal("2"),
        cost_basis_usd=Decimal("6000"),
        acquisition_date="2025-01-01T00:00:00",
        source="swap",
        tx_hash="0xlot1",
    )
    # BTC lot at a loss (bought at $50000, currently $40000)
    repo.insert(
        token="BTC",
        amount=Decimal("1"),
        cost_basis_usd=Decimal("50000"),
        acquisition_date="2024-01-01T00:00:00",
        source="swap",
        tx_hash="0xlot2",
    )
    # SOL lot at a gain (should be excluded from harvest)
    repo.insert(
        token="SOL",
        amount=Decimal("100"),
        cost_basis_usd=Decimal("1000"),
        acquisition_date="2025-02-01T00:00:00",
        source="swap",
        tx_hash="0xlot3",
    )


# ── Form 8949 ─────────────────────────────────────────────────────────────────

class TestForm8949:
    def test_box_code_short_term_self_reported(self):
        assert _box_code("short", is_reported=False, has_basis=False) == "C"

    def test_box_code_long_term_self_reported(self):
        assert _box_code("long", is_reported=False, has_basis=False) == "F"

    def test_box_code_short_term_1099_with_basis(self):
        assert _box_code("short", is_reported=True, has_basis=True) == "A"

    def test_box_code_long_term_1099_with_basis(self):
        assert _box_code("long", is_reported=True, has_basis=True) == "D"

    def test_generate_separates_short_and_long_term(self, db):
        _seed_disposals(db)
        gen = Form8949Generator(db)
        short_term, long_term = gen.generate(2025, "FIFO")

        assert len(short_term) == 2  # ETH gain + SOL loss
        assert len(long_term) == 1   # BTC gain

        for line in short_term:
            assert line.holding_period == "short"
            assert line.box == "C"  # self-reported
        for line in long_term:
            assert line.holding_period == "long"
            assert line.box == "F"

    def test_form_8949_line_values_are_decimal(self, db):
        _seed_disposals(db)
        gen = Form8949Generator(db)
        short_term, long_term = gen.generate(2025, "FIFO")

        for line in short_term + long_term:
            assert isinstance(line.proceeds, Decimal)
            assert isinstance(line.cost_basis, Decimal)
            assert isinstance(line.gain_loss, Decimal)

    def test_csv_output_has_correct_headers(self, db):
        _seed_disposals(db)
        gen = Form8949Generator(db)
        csv_str = gen.to_csv(2025, "FIFO")

        reader = csv.reader(io.StringIO(csv_str))
        headers = next(reader)
        assert "Part" in headers
        assert "Box" in headers
        assert "Description" in headers
        assert "Date Sold" in headers
        assert "Proceeds" in headers
        assert "Cost Basis" in headers
        assert "Gain or Loss" in headers
        assert "1099-DA Reported" in headers

    def test_csv_output_row_count(self, db):
        _seed_disposals(db)
        gen = Form8949Generator(db)
        csv_str = gen.to_csv(2025, "FIFO")

        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        # 1 header + 2 short-term + 1 long-term = 4
        assert len(rows) == 4

    def test_summary_totals(self, db):
        _seed_disposals(db)
        gen = Form8949Generator(db)
        summary = gen.summary(2025, "FIFO")

        st = summary["part_i_short_term"]
        lt = summary["part_ii_long_term"]

        assert st["count"] == 2
        assert st["gain_loss"] == Decimal("700")  # 1000 + (-300)
        assert lt["count"] == 1
        assert lt["gain_loss"] == Decimal("10000")

    def test_broker_flagging(self, db):
        _seed_disposals(db)
        gen = Form8949Generator(db)
        broker_map = {"0xshort1": "Coinbase"}
        short_term, long_term = gen.generate(2025, "FIFO", broker_map)

        reported = [l for l in short_term if l.is_1099_reported]
        assert len(reported) == 1
        assert reported[0].tx_hash == "0xshort1"
        assert reported[0].box == "A"  # short-term, reported with basis


# ── Schedule D ─────────────────────────────────────────────────────────────────

class TestScheduleD:
    def test_schedule_d_totals_match_form_8949(self, db):
        _seed_disposals(db)
        gen = ScheduleDGenerator(db)
        result = gen.generate(2025, "FIFO")

        # Short-term: $3000 + $500 proceeds, $2000 + $800 cost
        assert result.short_term_proceeds == Decimal("3500")
        assert result.short_term_cost_basis == Decimal("2800")
        assert result.short_term_net == Decimal("700")

        # Long-term
        assert result.long_term_proceeds == Decimal("25000")
        assert result.long_term_cost_basis == Decimal("15000")
        assert result.long_term_net == Decimal("10000")

        assert result.net_capital_gain_loss == Decimal("10700")

    def test_schedule_d_loss_deduction_cap(self, db):
        """Net loss capped at $3000 deduction."""
        repo = DisposalRepository(db)
        repo.insert(
            token="ETH", amount=Decimal("10"),
            proceeds_usd=Decimal("1000"), cost_basis_usd=Decimal("10000"),
            gain_loss_usd=Decimal("-9000"), holding_period="short",
            method="FIFO", disposal_date="2025-06-01T12:00:00", tx_hash="0xloss",
        )
        gen = ScheduleDGenerator(db)
        result = gen.generate(2025, "FIFO")

        assert result.net_capital_gain_loss == Decimal("-9000")
        assert result.deductible_loss == Decimal("-3000")
        assert result.carryover_loss == Decimal("6000")

    def test_schedule_d_no_loss_deduction_on_gain(self, db):
        _seed_disposals(db)
        gen = ScheduleDGenerator(db)
        result = gen.generate(2025, "FIFO")

        # Net is positive, so no deductible loss
        assert result.deductible_loss == Decimal("0")
        assert result.carryover_loss == Decimal("0")

    def test_prior_year_carryover(self, db):
        repo = DisposalRepository(db)
        repo.insert(
            token="ETH", amount=Decimal("1"),
            proceeds_usd=Decimal("2000"), cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("-1000"), holding_period="short",
            method="FIFO", disposal_date="2025-06-01T12:00:00", tx_hash="0xloss2",
        )
        gen = ScheduleDGenerator(db)
        result = gen.generate(2025, "FIFO", prior_year_carryover=Decimal("5000"))

        # short_term_net = -1000 - 5000 = -6000
        assert result.short_term_net == Decimal("-6000")

    def test_as_dict_output(self, db):
        _seed_disposals(db)
        gen = ScheduleDGenerator(db)
        result = gen.generate(2025, "FIFO")
        d = result.as_dict()

        assert d["year"] == 2025
        assert d["method"] == "FIFO"
        assert "short_term" in d
        assert "long_term" in d


# ── TurboTax CSV ───────────────────────────────────────────────────────────────

class TestTurboTaxExport:
    def test_csv_headers(self, db):
        _seed_disposals(db)
        exporter = TurboTaxExporter(db)
        csv_str = exporter.export(2025, "FIFO")

        reader = csv.reader(io.StringIO(csv_str))
        headers = next(reader)
        expected = [
            "Date Sold", "Currency Name", "Purchase Date",
            "Cost Basis", "Proceeds", "Gain or Loss",
            "Holding Period", "Amount Sold",
        ]
        assert headers == expected

    def test_csv_row_count(self, db):
        _seed_disposals(db)
        exporter = TurboTaxExporter(db)
        csv_str = exporter.export(2025, "FIFO")

        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        # 1 header + 3 disposals
        assert len(rows) == 4

    def test_csv_date_format(self, db):
        _seed_disposals(db)
        exporter = TurboTaxExporter(db)
        csv_str = exporter.export(2025, "FIFO")

        reader = csv.reader(io.StringIO(csv_str))
        next(reader)  # skip headers
        row = next(reader)
        date_sold = row[0]
        # Expect MM/DD/YYYY format
        assert "/" in date_sold
        parts = date_sold.split("/")
        assert len(parts) == 3
        assert len(parts[2]) == 4  # 4-digit year

    def test_holding_period_title_case(self, db):
        _seed_disposals(db)
        exporter = TurboTaxExporter(db)
        csv_str = exporter.export(2025, "FIFO")

        reader = csv.reader(io.StringIO(csv_str))
        next(reader)
        for row in reader:
            hp = row[6]
            assert hp in ("Short", "Long"), f"Unexpected holding period: {hp}"

    def test_full_detail_export(self, db):
        _seed_disposals(db)
        exporter = TurboTaxExporter(db)
        csv_str = exporter.export_full_detail(2025, "FIFO")

        reader = csv.reader(io.StringIO(csv_str))
        headers = next(reader)
        assert "TX Hash" in headers
        assert "Method" in headers


# ── Harvest suggestions ────────────────────────────────────────────────────────

class TestHarvestSuggestions:
    def test_suggestions_sorted_by_savings_desc(self, db):
        _seed_lots(db)
        analyzer = HarvestAnalyzer(db)
        current_prices = {
            "ETH": Decimal("2000"),   # cost $3000/unit → loss
            "BTC": Decimal("40000"),  # cost $50000/unit → loss
            "SOL": Decimal("20"),     # cost $10/unit → gain (excluded)
        }
        suggestions = analyzer.analyze(current_prices)

        assert len(suggestions) == 2  # only ETH and BTC have losses
        # BTC loss ($10000) > ETH loss ($2000) → BTC first
        assert suggestions[0].token == "BTC"
        assert suggestions[1].token == "ETH"
        # Sorted by savings desc
        assert suggestions[0].potential_tax_savings >= suggestions[1].potential_tax_savings

    def test_gain_positions_excluded(self, db):
        _seed_lots(db)
        analyzer = HarvestAnalyzer(db)
        current_prices = {
            "ETH": Decimal("2000"),
            "BTC": Decimal("40000"),
            "SOL": Decimal("20"),  # gain position
        }
        suggestions = analyzer.analyze(current_prices)
        tokens = {s.token for s in suggestions}
        assert "SOL" not in tokens

    def test_unrealized_loss_is_negative(self, db):
        _seed_lots(db)
        analyzer = HarvestAnalyzer(db)
        current_prices = {"ETH": Decimal("2000"), "BTC": Decimal("40000")}
        suggestions = analyzer.analyze(current_prices)

        for s in suggestions:
            assert s.unrealized_loss_usd < Decimal("0")

    def test_potential_savings_is_positive(self, db):
        _seed_lots(db)
        analyzer = HarvestAnalyzer(db)
        current_prices = {"ETH": Decimal("2000"), "BTC": Decimal("40000")}
        suggestions = analyzer.analyze(current_prices)

        for s in suggestions:
            assert s.potential_tax_savings > Decimal("0")

    def test_holding_period_classification(self, db):
        _seed_lots(db)
        analyzer = HarvestAnalyzer(db)
        current_prices = {"ETH": Decimal("2000"), "BTC": Decimal("40000")}
        from datetime import datetime, timezone
        suggestions = analyzer.analyze(
            current_prices,
            as_of_date=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )

        for s in suggestions:
            if s.token == "ETH":
                assert s.holding_period == "short"  # bought 2025-01-01, ~6 months
            elif s.token == "BTC":
                assert s.holding_period == "long"   # bought 2024-01-01, >1 year

    def test_as_dict_roundtrip(self, db):
        _seed_lots(db)
        analyzer = HarvestAnalyzer(db)
        current_prices = {"ETH": Decimal("2000"), "BTC": Decimal("40000")}
        suggestions = analyzer.analyze(current_prices)

        for s in suggestions:
            d = s.as_dict()
            assert "token" in d
            assert "unrealized_loss_usd" in d
            assert "potential_tax_savings" in d
