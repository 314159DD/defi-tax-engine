"""
Comprehensive tests for the country-specific tax module system.

Tests cover:
  - TaxModule registry (get_tax_module, get_supported_countries)
  - USTaxModule: methods, holding period, no exemptions, liability
  - GermanTaxModule: FIFO only, Spekulationsfrist, Freigrenze cliff,
    tax brackets, currency formatting
  - Report generation: Anlage SO CSV, WISO CSV, DATEV CSV
  - Integration with CalculatorEngine
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.tax import get_tax_module, get_supported_countries
from src.tax.models import Exemption, HoldingPeriod, ReportFile, TaxSummary
from src.tax.us.module import USTaxModule
from src.tax.de.module import GermanTaxModule, _calculate_german_income_tax


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestTaxModuleRegistry:
    def test_get_us_module(self):
        module = get_tax_module("US")
        assert isinstance(module, USTaxModule)
        assert module.country_code == "US"
        assert module.currency_code == "USD"

    def test_get_de_module(self):
        module = get_tax_module("DE")
        assert isinstance(module, GermanTaxModule)
        assert module.country_code == "DE"
        assert module.currency_code == "EUR"

    def test_case_insensitive(self):
        module = get_tax_module("us")
        assert isinstance(module, USTaxModule)

    def test_unsupported_country_raises(self):
        with pytest.raises(ValueError, match="Unsupported country code"):
            get_tax_module("XX")

    def test_supported_countries_list(self):
        countries = get_supported_countries()
        codes = [c["code"] for c in countries]
        assert "US" in codes
        assert "DE" in codes


# ---------------------------------------------------------------------------
# US Module tests
# ---------------------------------------------------------------------------

class TestUSTaxModule:
    def setup_method(self):
        self.module = USTaxModule()

    def test_cost_basis_methods(self):
        methods = self.module.get_cost_basis_methods()
        assert methods == ["FIFO", "LIFO", "HIFO"]

    def test_default_method(self):
        assert self.module.get_default_method() == "FIFO"

    def test_holding_period_short_term_364_days(self):
        """364 days = short-term in US."""
        acquired = date(2025, 1, 1)
        disposed = date(2025, 12, 31)  # 364 days
        assert self.module.classify_holding_period(acquired, disposed) == HoldingPeriod.SHORT_TERM

    def test_holding_period_short_term_365_days(self):
        """365 days = still short-term in US (need >365 = 366+)."""
        acquired = date(2025, 1, 1)
        disposed = date(2026, 1, 1)  # 365 days
        assert self.module.classify_holding_period(acquired, disposed) == HoldingPeriod.SHORT_TERM

    def test_holding_period_long_term_366_days(self):
        """366 days = long-term in US."""
        acquired = date(2025, 1, 1)
        disposed = date(2026, 1, 2)  # 366 days
        assert self.module.classify_holding_period(acquired, disposed) == HoldingPeriod.LONG_TERM

    def test_no_exemptions(self):
        """US has no crypto exemptions."""
        exemptions = self.module.get_exemptions([], 2025)
        assert exemptions == []

    def test_format_currency(self):
        assert self.module.format_currency(Decimal("1234.56")) == "$1,234.56"
        assert self.module.format_currency(Decimal("0")) == "$0.00"
        assert self.module.format_currency(Decimal("-500.10")) == "-$500.10"

    def test_calculate_liability_with_bracket(self):
        """User-provided bracket override."""
        tax = self.module.calculate_liability(
            gains=Decimal("10000"),
            income=Decimal("0"),
            user_bracket=Decimal("0.37"),
        )
        assert tax == Decimal("3700.00")

    def test_calculate_liability_default(self):
        """Default estimate (15% gains, 24% income)."""
        tax = self.module.calculate_liability(
            gains=Decimal("10000"),
            income=Decimal("5000"),
        )
        # 10000 * 0.15 + 5000 * 0.24 = 1500 + 1200 = 2700
        assert tax == Decimal("2700.00")

    def test_income_categories(self):
        cats = self.module.get_income_categories()
        names = [c.name for c in cats]
        assert "Staking Rewards" in names
        assert "Airdrops" in names

    def test_generate_reports_returns_files(self):
        """Reports should return ReportFile objects even with empty data."""
        reports = self.module.generate_reports(
            disposals=[], income_events=[], year=2025, method="FIFO"
        )
        assert len(reports) == 4
        types = [r.report_type for r in reports]
        assert "form_8949" in types
        assert "schedule_d" in types
        assert "turbotax" in types
        assert "income" in types


# ---------------------------------------------------------------------------
# German Module tests
# ---------------------------------------------------------------------------

class TestGermanTaxModule:
    def setup_method(self):
        self.module = GermanTaxModule()

    def test_cost_basis_methods_fifo_only(self):
        """German tax law only allows FIFO for filing."""
        methods = self.module.get_cost_basis_methods()
        assert methods == ["FIFO"]

    def test_comparison_methods(self):
        """What-if analysis allows additional methods."""
        methods = self.module.get_comparison_methods()
        assert "LIFO" in methods
        assert "HIFO" in methods

    def test_default_method(self):
        assert self.module.get_default_method() == "FIFO"

    def test_spekulationsfrist_365_days_still_taxable(self):
        """Held exactly 365 days = still taxable (short-term)."""
        acquired = date(2025, 1, 1)
        disposed = date(2026, 1, 1)  # exactly 365 days
        assert self.module.classify_holding_period(acquired, disposed) == HoldingPeriod.SHORT_TERM

    def test_spekulationsfrist_366_days_exempt(self):
        """Held 366 days = exempt (Spekulationsfrist passed)."""
        acquired = date(2025, 1, 1)
        disposed = date(2026, 1, 2)  # 366 days
        assert self.module.classify_holding_period(acquired, disposed) == HoldingPeriod.EXEMPT

    def test_spekulationsfrist_1_day(self):
        """Held 1 day = short-term."""
        acquired = date(2025, 6, 1)
        disposed = date(2025, 6, 2)
        assert self.module.classify_holding_period(acquired, disposed) == HoldingPeriod.SHORT_TERM

    # ── Freigrenze tests (the CLIFF!) ──────────────────────────────────

    def _make_disposal(self, gain: Decimal, hp: HoldingPeriod = HoldingPeriod.SHORT_TERM) -> SimpleNamespace:
        return SimpleNamespace(
            date=datetime(2025, 6, 15),
            holding_period=hp,
            gain_loss_usd=gain,
            tx_hash=f"tx_{gain}",
        )

    def test_freigrenze_under_all_exempt(self):
        """Total gains EUR 999 < EUR 1,000 = ALL disposals exempt."""
        disposals = [
            self._make_disposal(Decimal("500")),
            self._make_disposal(Decimal("499")),
        ]
        exemptions = self.module.get_exemptions(disposals, 2025)
        freigrenze_exemptions = [e for e in exemptions if "Freigrenze" in e.reason]
        assert len(freigrenze_exemptions) == 2  # both disposals exempted

    def test_freigrenze_at_limit_all_taxable(self):
        """Total gains EUR 1,000 = ALL disposals TAXABLE (Freigrenze is a cliff!)."""
        disposals = [
            self._make_disposal(Decimal("500")),
            self._make_disposal(Decimal("500")),
        ]
        exemptions = self.module.get_exemptions(disposals, 2025)
        freigrenze_exemptions = [e for e in exemptions if "Freigrenze" in e.reason]
        assert len(freigrenze_exemptions) == 0  # NO exemptions - cliff hit

    def test_freigrenze_over_all_taxable(self):
        """Total gains EUR 1,001 = ALL disposals TAXABLE."""
        disposals = [
            self._make_disposal(Decimal("600")),
            self._make_disposal(Decimal("401")),
        ]
        exemptions = self.module.get_exemptions(disposals, 2025)
        freigrenze_exemptions = [e for e in exemptions if "Freigrenze" in e.reason]
        assert len(freigrenze_exemptions) == 0

    def test_spekulationsfrist_exemption_tagged(self):
        """Long-term disposals get Spekulationsfrist exemption."""
        disposals = [
            self._make_disposal(Decimal("5000"), HoldingPeriod.EXEMPT),
        ]
        exemptions = self.module.get_exemptions(disposals, 2025)
        spek_exemptions = [e for e in exemptions if "Spekulationsfrist" in e.reason]
        assert len(spek_exemptions) == 1

    def test_mixed_exempt_and_short_term(self):
        """Exempt disposals + short-term under Freigrenze = both get exemptions."""
        disposals = [
            self._make_disposal(Decimal("800"), HoldingPeriod.SHORT_TERM),
            self._make_disposal(Decimal("5000"), HoldingPeriod.EXEMPT),
        ]
        exemptions = self.module.get_exemptions(disposals, 2025)
        # 1 Spekulationsfrist + 1 Freigrenze (800 < 1000)
        spek = [e for e in exemptions if "Spekulationsfrist" in e.reason]
        frg = [e for e in exemptions if "Freigrenze" in e.reason]
        assert len(spek) == 1
        assert len(frg) == 1

    # ── German tax bracket tests ───────────────────────────────────────

    def test_bracket_grundfreibetrag(self):
        """Income up to EUR 11,784 = 0% tax."""
        tax = _calculate_german_income_tax(Decimal("11784"))
        assert tax == Decimal("0")

    def test_bracket_zero(self):
        tax = _calculate_german_income_tax(Decimal("0"))
        assert tax == Decimal("0")

    def test_bracket_zone2(self):
        """EUR 15,000 should be in 14-24% zone."""
        tax = _calculate_german_income_tax(Decimal("15000"))
        assert tax > Decimal("0")
        assert tax < Decimal("15000") * Decimal("0.24")

    def test_bracket_zone3(self):
        """EUR 50,000 should be in 24-42% zone."""
        tax = _calculate_german_income_tax(Decimal("50000"))
        assert tax > Decimal("0")
        # Should be less than 42% of total
        assert tax < Decimal("50000") * Decimal("0.42")

    def test_bracket_zone4_42pct(self):
        """EUR 100,000 should be in 42% zone."""
        tax = _calculate_german_income_tax(Decimal("100000"))
        assert tax > Decimal("0")
        # Effective rate should be between ~30-42%
        effective_rate = tax / Decimal("100000")
        assert Decimal("0.25") < effective_rate < Decimal("0.42")

    def test_bracket_zone5_reichensteuer(self):
        """EUR 300,000 should hit 45% Reichensteuer zone."""
        tax = _calculate_german_income_tax(Decimal("300000"))
        assert tax > Decimal("0")
        # Effective rate approaches but doesn't reach 45%
        effective_rate = tax / Decimal("300000")
        assert effective_rate > Decimal("0.35")
        assert effective_rate < Decimal("0.45")

    def test_solidaritaetszuschlag_added(self):
        """Total liability should include 5.5% Soli on top of income tax."""
        tax_only = _calculate_german_income_tax(Decimal("50000"))
        total = self.module.calculate_liability(
            gains=Decimal("50000"),
            income=Decimal("0"),
        )
        # Soli is 5.5% of tax, so total should be ~1.055x the income tax
        # Allow 1 cent rounding tolerance
        expected_min = tax_only + (tax_only * Decimal("0.055")).quantize(Decimal("0.01")) - Decimal("0.01")
        expected_max = tax_only + (tax_only * Decimal("0.055")).quantize(Decimal("0.01")) + Decimal("0.01")
        assert expected_min <= total <= expected_max

    def test_liability_with_bracket_override(self):
        """User-provided bracket + Soli."""
        total = self.module.calculate_liability(
            gains=Decimal("10000"),
            income=Decimal("0"),
            user_bracket=Decimal("0.42"),
        )
        tax = (Decimal("10000") * Decimal("0.42")).quantize(Decimal("0.01"))
        soli = (tax * Decimal("0.055")).quantize(Decimal("0.01"))
        assert total == tax + soli

    # ── Currency formatting ────────────────────────────────────────────

    def test_format_currency_german(self):
        result = self.module.format_currency(Decimal("1234.56"))
        # Should use German format: 1.234,56 EUR
        assert "1.234" in result
        assert ",56" in result

    def test_format_currency_zero(self):
        result = self.module.format_currency(Decimal("0"))
        assert "0,00" in result

    # ── Freigrenze status helper ───────────────────────────────────────

    def test_freigrenze_status_under(self):
        disposals = [self._make_disposal(Decimal("500"))]
        status = self.module.get_freigrenze_status(disposals, 2025)
        assert status["status"] == "under"
        assert Decimal(status["remaining"]) == Decimal("500")

    def test_freigrenze_status_over(self):
        disposals = [self._make_disposal(Decimal("1500"))]
        status = self.module.get_freigrenze_status(disposals, 2025)
        assert status["status"] == "over"
        assert Decimal(status["remaining"]) == Decimal("0")

    # ── Income categories ──────────────────────────────────────────────

    def test_income_categories_german(self):
        cats = self.module.get_income_categories()
        names = [c.name for c in cats]
        assert "Staking Rewards" in names
        # German law references
        citations = [c.citation for c in cats]
        assert any("\u00a722" in c for c in citations)  # §22

    # ── Report generation ──────────────────────────────────────────────

    def test_generate_reports_returns_de_files(self):
        reports = self.module.generate_reports(
            disposals=[], income_events=[], year=2025, method="FIFO"
        )
        assert len(reports) == 3
        types = [r.report_type for r in reports]
        assert "anlage_so" in types
        assert "wiso" in types
        assert "datev" in types


# ---------------------------------------------------------------------------
# Anlage SO CSV format tests
# ---------------------------------------------------------------------------

class TestAnlageSO:
    def test_anlage_so_csv_structure(self):
        """Anlage SO CSV should have proper German column headers."""
        from src.tax.de.anlage_so import generate_anlage_so_csv

        disposal = SimpleNamespace(
            date=datetime(2025, 6, 15),
            token="ETH",
            amount=Decimal("1.5"),
            proceeds_usd=Decimal("5000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("2000"),
            holding_period=HoldingPeriod.SHORT_TERM,
            tx_hash="0xabc123",
        )

        csv_str = generate_anlage_so_csv([disposal], [], 2025)
        assert "Anlage SO" in csv_str
        assert "Veraeusserungspreis" in csv_str
        assert "Anschaffungskosten" in csv_str
        assert "ETH" in csv_str

    def test_anlage_so_includes_income_section(self):
        """Anlage SO should include Sonstige Einkuenfte section."""
        from src.tax.de.anlage_so import generate_anlage_so_csv

        income = {
            "date": "2025-03-15",
            "tx_type": "reward",
            "token": "ETH",
            "amount": "0.5",
            "usd_value": Decimal("1500"),
            "tx_hash": "0xdef456",
            "chain": "ethereum",
        }

        csv_str = generate_anlage_so_csv([], [income], 2025)
        assert "Sonstige Einkuenfte" in csv_str
        assert "Staking Reward" in csv_str


# ---------------------------------------------------------------------------
# WISO export format tests
# ---------------------------------------------------------------------------

class TestWISOExport:
    def test_wiso_csv_columns(self):
        """WISO CSV should have the expected columns."""
        from src.tax.de.wiso_export import generate_wiso_csv

        disposal = SimpleNamespace(
            date=datetime(2025, 6, 15),
            token="BTC",
            amount=Decimal("0.1"),
            proceeds_usd=Decimal("6000"),
            cost_basis_usd=Decimal("5000"),
            gain_loss_usd=Decimal("1000"),
            holding_period=HoldingPeriod.SHORT_TERM,
            tx_hash="0xwiso123",
            lots_consumed=[],
        )

        csv_str = generate_wiso_csv([disposal], 2025)
        assert "Kaufdatum" in csv_str
        assert "Verkaufsdatum" in csv_str
        assert "Gewinn/Verlust" in csv_str

    def test_wiso_exempt_type(self):
        """Exempt disposals should be marked as 'Steuerfrei'."""
        from src.tax.de.wiso_export import generate_wiso_csv

        disposal = SimpleNamespace(
            date=datetime(2025, 6, 15),
            token="ETH",
            amount=Decimal("2"),
            proceeds_usd=Decimal("8000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("5000"),
            holding_period=HoldingPeriod.EXEMPT,
            tx_hash="0xexempt",
            lots_consumed=[],
        )

        csv_str = generate_wiso_csv([disposal], 2025)
        assert "Steuerfrei" in csv_str


# ---------------------------------------------------------------------------
# DATEV export format tests
# ---------------------------------------------------------------------------

class TestDATEVExport:
    def test_datev_csv_columns(self):
        """DATEV CSV should have standard Buchungssatz columns."""
        from src.tax.de.datev_export import generate_datev_csv

        disposal = SimpleNamespace(
            date=datetime(2025, 6, 15),
            token="ETH",
            amount=Decimal("1"),
            proceeds_usd=Decimal("4000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("1000"),
            holding_period=HoldingPeriod.SHORT_TERM,
            tx_hash="0xdatev123",
        )

        csv_str = generate_datev_csv([disposal], 2025)
        assert "Soll/Haben" in csv_str
        assert "Konto" in csv_str
        assert "Buchungstext" in csv_str

    def test_datev_gain_uses_haben(self):
        """Gains should be credited (Haben)."""
        from src.tax.de.datev_export import generate_datev_csv

        disposal = SimpleNamespace(
            date=datetime(2025, 6, 15),
            token="BTC",
            amount=Decimal("0.5"),
            proceeds_usd=Decimal("5000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("2000"),
            holding_period=HoldingPeriod.SHORT_TERM,
            tx_hash="0xgain",
        )

        csv_str = generate_datev_csv([disposal], 2025)
        # Read back CSV
        reader = csv.reader(io.StringIO(csv_str), delimiter=";")
        rows = list(reader)
        # Header + 1 data row
        assert len(rows) == 2
        assert rows[1][1] == "H"  # Haben for gain
        assert rows[1][2] == "2740"  # Veraeusserungsgewinne

    def test_datev_loss_uses_soll(self):
        """Losses should be debited (Soll)."""
        from src.tax.de.datev_export import generate_datev_csv

        disposal = SimpleNamespace(
            date=datetime(2025, 6, 15),
            token="ETH",
            amount=Decimal("1"),
            proceeds_usd=Decimal("2000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("-1000"),
            holding_period=HoldingPeriod.SHORT_TERM,
            tx_hash="0xloss",
        )

        csv_str = generate_datev_csv([disposal], 2025)
        reader = csv.reader(io.StringIO(csv_str), delimiter=";")
        rows = list(reader)
        assert rows[1][1] == "S"  # Soll for loss
        assert rows[1][2] == "2750"  # Veraeusserungsverluste


# ---------------------------------------------------------------------------
# Shared models tests
# ---------------------------------------------------------------------------

class TestTaxModels:
    def test_holding_period_enum_values(self):
        assert HoldingPeriod.SHORT_TERM.value == "short-term"
        assert HoldingPeriod.LONG_TERM.value == "long-term"
        assert HoldingPeriod.EXEMPT.value == "exempt"

    def test_exemption_requires_decimal(self):
        with pytest.raises(TypeError):
            Exemption(
                disposal_id="tx1",
                reason="test",
                citation_code="test",
                citation_text="test",
                exempt_amount=1000,  # type: ignore - should be Decimal
            )

    def test_tax_summary_as_dict(self):
        summary = TaxSummary(
            total_gains=Decimal("5000"),
            total_losses=Decimal("-2000"),
            net=Decimal("3000"),
        )
        d = summary.as_dict()
        assert d["total_gains"] == "5000"
        assert d["net"] == "3000"

    def test_report_file_content_bytes(self):
        rf = ReportFile(
            filename="test.csv",
            content="hello,world",
            mime_type="text/csv",
            report_type="test",
        )
        assert rf.content_bytes == b"hello,world"


# ---------------------------------------------------------------------------
# Integration: CalculatorEngine + TaxModule
# ---------------------------------------------------------------------------

class TestEngineWithTaxModule:
    def test_engine_accepts_us_module(self):
        from src.calculator.engine import CalculatorEngine
        module = USTaxModule()
        engine = CalculatorEngine(method="FIFO", tax_module=module)
        assert engine.method == "FIFO"
        assert engine.tax_module is module

    def test_engine_accepts_de_module(self):
        from src.calculator.engine import CalculatorEngine
        module = GermanTaxModule()
        engine = CalculatorEngine(method="FIFO", tax_module=module)
        assert engine.method == "FIFO"

    def test_engine_rejects_invalid_method_for_de(self):
        """LIFO is not allowed for German filing."""
        from src.calculator.engine import CalculatorEngine
        module = GermanTaxModule()
        with pytest.raises(ValueError, match="not allowed for DE"):
            CalculatorEngine(method="LIFO", tax_module=module)

    def test_engine_allows_all_us_methods(self):
        from src.calculator.engine import CalculatorEngine
        module = USTaxModule()
        for method in ("FIFO", "LIFO", "HIFO"):
            engine = CalculatorEngine(method=method, tax_module=module)
            assert engine.method == method

    def test_engine_without_module_still_works(self):
        """Backward compatibility: no tax_module = legacy behavior."""
        from src.calculator.engine import CalculatorEngine
        engine = CalculatorEngine(method="HIFO")
        assert engine.method == "HIFO"
        assert engine.tax_module is None
