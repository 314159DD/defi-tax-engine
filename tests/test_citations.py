"""
Tests for Sprint 4.3: Transparent Tax Logic.

Covers:
  - Citation database (all codes resolve, country filtering)
  - US module citation tagging on disposals and income events
  - DE module citation tagging (Spekulationsfrist, Freigrenze, LP gray area)
  - Gray area flag correctness
  - Methodology statements for both countries
  - Disposal dataclass citation fields
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.tax.citations import (
    CITATIONS,
    CitationCode,
    get_citation,
    get_citations_for_country,
)
from src.tax.methodology import get_methodology_statement
from src.tax.models import HoldingPeriod
from src.tax.us.module import USTaxModule
from src.tax.de.module import GermanTaxModule
from src.calculator.lots import Disposal, LotConsumption


# ---------------------------------------------------------------------------
# Citation database tests
# ---------------------------------------------------------------------------

class TestCitationDatabase:
    def test_all_citation_codes_resolve(self):
        """Every CitationCode enum member must have an entry in CITATIONS."""
        for code in CitationCode:
            result = get_citation(code)
            assert "code" in result
            assert "text" in result
            assert "source" in result
            assert "is_gray_area" in result
            assert result["code"] == code.value

    def test_citation_texts_are_nonempty(self):
        for code in CitationCode:
            result = get_citation(code)
            assert len(result["text"]) > 10, f"Citation text too short for {code}"
            assert len(result["source"]) > 5, f"Citation source too short for {code}"

    def test_unknown_code_raises_keyerror(self):
        with pytest.raises(KeyError):
            get_citation("NONEXISTENT")  # type: ignore

    def test_us_citations_count(self):
        us = get_citations_for_country("US")
        assert len(us) == 7  # 7 US citation codes
        for code in us:
            assert code.value.startswith("US_")

    def test_de_citations_count(self):
        de = get_citations_for_country("DE")
        assert len(de) == 8  # 8 DE citation codes
        for code in de:
            assert code.value.startswith("DE_")

    def test_country_filter_case_insensitive(self):
        us_lower = get_citations_for_country("us")
        us_upper = get_citations_for_country("US")
        assert us_lower == us_upper

    def test_empty_country_returns_nothing(self):
        result = get_citations_for_country("XX")
        assert len(result) == 0

    def test_gray_area_flags(self):
        """Only specific citations should be gray areas."""
        gray_codes = {
            code for code, data in CITATIONS.items() if data["is_gray_area"]
        }
        assert CitationCode.US_WASH_SALE_WARNING in gray_codes
        assert CitationCode.DE_LP_DEPOSIT_GRAY_AREA in gray_codes
        # Non-gray-area codes should not be flagged
        assert CitationCode.US_SHORT_TERM_GAIN not in gray_codes
        assert CitationCode.DE_SPEKULATIONSFRIST_EXEMPT not in gray_codes

    def test_us_citations_reference_irs(self):
        """US citations should reference IRS sources."""
        us = get_citations_for_country("US")
        for code, data in us.items():
            source = data["source"]
            # Every US citation should reference IRC, IRS, Notice, Revenue Ruling, or general principles
            assert any(
                keyword in source
                for keyword in ("IRC", "IRS", "Notice", "Revenue Ruling", "Internal Revenue Code", "General", "general")
            ), f"{code}: source '{source}' does not reference IRS"

    def test_de_citations_reference_german_law(self):
        """DE citations should reference EStG or BMF."""
        de = get_citations_for_country("DE")
        for code, data in de.items():
            source = data["source"]
            assert any(
                keyword in source
                for keyword in ("\u00a7", "EStG", "BMF", "Allgemeine")
            ), f"{code}: source '{source}' does not reference German law"


# ---------------------------------------------------------------------------
# Disposal dataclass citation fields
# ---------------------------------------------------------------------------

class TestDisposalCitationFields:
    def test_disposal_default_citation_fields(self):
        """New citation fields should default to None/False."""
        d = Disposal(
            date=datetime(2025, 6, 15),
            token="ETH",
            amount=Decimal("1"),
            proceeds_usd=Decimal("4000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("1000"),
            holding_period="short-term",
            method="FIFO",
            lots_consumed=[],
            tx_hash="0xtest",
        )
        assert d.citation_code is None
        assert d.citation_text is None
        assert d.citation_source is None
        assert d.is_gray_area is False

    def test_disposal_with_citation_fields(self):
        """Citation fields can be set via constructor."""
        d = Disposal(
            date=datetime(2025, 6, 15),
            token="ETH",
            amount=Decimal("1"),
            proceeds_usd=Decimal("4000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("1000"),
            holding_period="short-term",
            method="FIFO",
            lots_consumed=[],
            tx_hash="0xtest",
            citation_code="US_SHORT_TERM_GAIN",
            citation_text="IRC \u00a71222(1)",
            citation_source="IRC",
            is_gray_area=False,
        )
        assert d.citation_code == "US_SHORT_TERM_GAIN"
        assert d.citation_text == "IRC \u00a71222(1)"

    def test_disposal_backward_compatible(self):
        """Existing code that creates Disposal without citation fields still works."""
        d = Disposal(
            date=datetime(2025, 6, 15),
            token="BTC",
            amount=Decimal("0.5"),
            proceeds_usd=Decimal("25000"),
            cost_basis_usd=Decimal("20000"),
            gain_loss_usd=Decimal("5000"),
            holding_period="long-term",
            method="FIFO",
            lots_consumed=[],
            tx_hash="0xbc",
        )
        # Should not raise, and fields should be defaults
        assert d.citation_code is None
        assert d.is_gray_area is False


# ---------------------------------------------------------------------------
# US Module citation tagging
# ---------------------------------------------------------------------------

class TestUSCitationTagging:
    def setup_method(self):
        self.module = USTaxModule()

    def _make_disposal(
        self,
        hp: str = "short-term",
        hp_enum: HoldingPeriod | None = None,
        source: str = "swap",
        tx_type: str = "swap",
    ) -> SimpleNamespace:
        return SimpleNamespace(
            date=datetime(2025, 6, 15),
            token="ETH",
            amount=Decimal("1"),
            proceeds_usd=Decimal("4000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=Decimal("1000"),
            holding_period=hp,
            holding_period_enum=hp_enum,
            method="FIFO",
            lots_consumed=[],
            tx_hash="0xtest",
            source=source,
            tx_type=tx_type,
            citation_code=None,
            citation_text=None,
            citation_source=None,
            is_gray_area=False,
        )

    def test_short_term_gain_citation(self):
        d = self._make_disposal(hp="short-term", hp_enum=HoldingPeriod.SHORT_TERM)
        self.module.tag_citations([d])
        assert d.citation_code == "US_SHORT_TERM_GAIN"
        assert "IRC" in d.citation_text
        assert "\u00a71222(1)" in d.citation_text
        assert d.is_gray_area is False

    def test_long_term_gain_citation(self):
        d = self._make_disposal(hp="long-term", hp_enum=HoldingPeriod.LONG_TERM)
        self.module.tag_citations([d])
        assert d.citation_code == "US_LONG_TERM_GAIN"
        assert "\u00a71222(3)" in d.citation_text
        assert d.is_gray_area is False

    def test_bridge_transfer_citation(self):
        d = self._make_disposal(source="bridge", tx_type="bridge")
        self.module.tag_citations([d])
        assert d.citation_code == "US_BRIDGE_TRANSFER"
        assert "Non-taxable" in d.citation_text
        assert d.is_gray_area is False

    def test_staking_income_citation(self):
        event = {"tx_type": "reward", "token": "ETH", "amount": "0.5"}
        self.module.tag_income_citations([event])
        assert event["citation_code"] == "US_STAKING_INCOME"
        assert "Rev. Rul. 2023-14" in event["citation_text"]

    def test_mining_income_citation(self):
        event = {"tx_type": "mining", "token": "BTC", "amount": "0.001"}
        self.module.tag_income_citations([event])
        assert event["citation_code"] == "US_MINING_INCOME"
        assert "Notice 2014-21" in event["citation_text"]

    def test_airdrop_income_citation(self):
        event = {"tx_type": "airdrop", "token": "UNI", "amount": "400"}
        self.module.tag_income_citations([event])
        assert event["citation_code"] == "US_AIRDROP_INCOME"
        assert "Rev. Rul. 2019-24" in event["citation_text"]

    def test_unknown_income_type_not_tagged(self):
        event = {"tx_type": "unknown_thing", "token": "X", "amount": "1"}
        self.module.tag_income_citations([event])
        assert "citation_code" not in event

    def test_generate_reports_tags_citations(self):
        """generate_reports should call tag_citations internally."""
        d = self._make_disposal(hp="short-term", hp_enum=HoldingPeriod.SHORT_TERM)
        # generate_reports mutates disposals by tagging
        self.module.generate_reports([d], [], 2025, "FIFO")
        assert d.citation_code == "US_SHORT_TERM_GAIN"


# ---------------------------------------------------------------------------
# DE Module citation tagging
# ---------------------------------------------------------------------------

class TestDECitationTagging:
    def setup_method(self):
        self.module = GermanTaxModule()

    def _make_disposal(
        self,
        gain: Decimal = Decimal("1000"),
        hp: HoldingPeriod = HoldingPeriod.SHORT_TERM,
        source: str = "swap",
        tx_type: str = "swap",
    ) -> SimpleNamespace:
        return SimpleNamespace(
            date=datetime(2025, 6, 15),
            token="ETH",
            amount=Decimal("1"),
            proceeds_usd=gain + Decimal("3000"),
            cost_basis_usd=Decimal("3000"),
            gain_loss_usd=gain,
            holding_period=hp.value,
            holding_period_enum=hp,
            method="FIFO",
            lots_consumed=[],
            tx_hash=f"tx_{gain}",
            source=source,
            tx_type=tx_type,
            citation_code=None,
            citation_text=None,
            citation_source=None,
            is_gray_area=False,
        )

    def test_spekulationsfrist_exempt_citation(self):
        d = self._make_disposal(gain=Decimal("5000"), hp=HoldingPeriod.EXEMPT)
        self.module.tag_citations([d], 2025)
        assert d.citation_code == "DE_SPEKULATIONSFRIST_EXEMPT"
        assert "\u00a723" in d.citation_text
        assert "Steuerfrei" in d.citation_text
        assert d.is_gray_area is False

    def test_spekulationsfrist_taxable_citation(self):
        """Short-term with gains >= Freigrenze -> taxable with Spekulationsfrist citation."""
        d = self._make_disposal(gain=Decimal("2000"), hp=HoldingPeriod.SHORT_TERM)
        self.module.tag_citations([d], 2025)
        # Gain is 2000 >= 1000, so Freigrenze exceeded
        assert d.citation_code == "DE_FREIGRENZE_EXCEEDED"
        assert d.is_gray_area is False

    def test_freigrenze_exempt_citation(self):
        """Short-term gains under EUR 1,000 -> Freigrenze exempt."""
        d = self._make_disposal(gain=Decimal("500"), hp=HoldingPeriod.SHORT_TERM)
        self.module.tag_citations([d], 2025)
        assert d.citation_code == "DE_FREIGRENZE_EXEMPT"
        assert "Freigrenze" in d.citation_text
        assert "1.000" in d.citation_text
        assert d.is_gray_area is False

    def test_freigrenze_exceeded_citation(self):
        """Short-term gains at exactly EUR 1,000 -> Freigrenze exceeded (cliff!)."""
        d1 = self._make_disposal(gain=Decimal("500"), hp=HoldingPeriod.SHORT_TERM)
        d2 = self._make_disposal(gain=Decimal("500"), hp=HoldingPeriod.SHORT_TERM)
        d2.tx_hash = "tx_500_b"
        self.module.tag_citations([d1, d2], 2025)
        # Total = 1000 EUR >= Freigrenze -> all taxable
        assert d1.citation_code == "DE_FREIGRENZE_EXCEEDED"
        assert d2.citation_code == "DE_FREIGRENZE_EXCEEDED"

    def test_lp_deposit_gray_area(self):
        d = self._make_disposal(
            gain=Decimal("1000"),
            hp=HoldingPeriod.SHORT_TERM,
            source="lp_add",
            tx_type="lp_add",
        )
        self.module.tag_citations([d], 2025)
        assert d.citation_code == "DE_LP_DEPOSIT_GRAY_AREA"
        assert d.is_gray_area is True
        assert "BMF" in d.citation_source
        assert "Rn. 68" in d.citation_source

    def test_bridge_transfer_citation(self):
        d = self._make_disposal(source="bridge", tx_type="bridge")
        self.module.tag_citations([d], 2025)
        assert d.citation_code == "DE_BRIDGE_TRANSFER"
        assert d.is_gray_area is False

    def test_staking_income_citation(self):
        event = {"tx_type": "reward", "token": "ETH", "amount": "0.5"}
        self.module.tag_income_citations([event])
        assert event["citation_code"] == "DE_STAKING_INCOME"
        assert "\u00a722 Nr. 3 EStG" in event["citation_text"]
        assert "BMF" in event["citation_source"]

    def test_generate_reports_tags_de_citations(self):
        """generate_reports should call tag_citations internally."""
        d = self._make_disposal(gain=Decimal("5000"), hp=HoldingPeriod.EXEMPT)
        self.module.generate_reports([d], [], 2025, "FIFO")
        assert d.citation_code == "DE_SPEKULATIONSFRIST_EXEMPT"

    def test_mixed_exempt_and_under_freigrenze(self):
        """Exempt + short-term under Freigrenze: both tagged correctly."""
        d_exempt = self._make_disposal(gain=Decimal("5000"), hp=HoldingPeriod.EXEMPT)
        d_short = self._make_disposal(gain=Decimal("800"), hp=HoldingPeriod.SHORT_TERM)
        self.module.tag_citations([d_exempt, d_short], 2025)
        assert d_exempt.citation_code == "DE_SPEKULATIONSFRIST_EXEMPT"
        assert d_short.citation_code == "DE_FREIGRENZE_EXEMPT"


# ---------------------------------------------------------------------------
# Methodology statements
# ---------------------------------------------------------------------------

class TestMethodologyStatements:
    def test_us_methodology_fifo(self):
        stmt = get_methodology_statement("US", "FIFO", 2025)
        assert "FIFO" in stmt
        assert "Notice 2014-21" in stmt
        assert "Revenue Ruling 2023-14" in stmt
        assert "Form 8949" in stmt
        assert "2025" in stmt

    def test_us_methodology_hifo(self):
        stmt = get_methodology_statement("US", "HIFO", 2025)
        assert "HIFO" in stmt

    def test_de_methodology_fifo(self):
        stmt = get_methodology_statement("DE", "FIFO", 2025)
        assert "FIFO" in stmt
        assert "BMF-Schreiben" in stmt
        assert "06.03.2025" in stmt
        assert "\u00a723" in stmt
        assert "2025" in stmt

    def test_de_methodology_contains_freigrenze(self):
        stmt = get_methodology_statement("DE", "FIFO", 2025)
        assert "1.000 EUR" in stmt
        assert "Freigrenze" in stmt

    def test_de_methodology_contains_staking_reference(self):
        stmt = get_methodology_statement("DE", "FIFO", 2025)
        assert "\u00a722 Nr. 3 EStG" in stmt

    def test_us_methodology_contains_disclaimer(self):
        stmt = get_methodology_statement("US", "FIFO", 2025)
        assert "does not constitute tax advice" in stmt

    def test_de_methodology_contains_disclaimer(self):
        stmt = get_methodology_statement("DE", "FIFO", 2025)
        assert "steuerliche Beratung" in stmt

    def test_unsupported_country_raises(self):
        with pytest.raises(ValueError, match="No methodology statement"):
            get_methodology_statement("XX", "FIFO", 2025)

    def test_case_insensitive(self):
        us = get_methodology_statement("us", "FIFO", 2025)
        assert "FIFO" in us

    def test_year_appears_in_statement(self):
        stmt_2026 = get_methodology_statement("US", "FIFO", 2026)
        assert "2026" in stmt_2026
