"""
US Tax Module - IRS rules for cryptocurrency taxation.

Rules:
  - Cost basis methods: FIFO, LIFO, HIFO (all permitted by IRS)
  - Holding period: <366 days = short-term, >=366 days = long-term
  - No exemptions (no equivalent of German Spekulationsfrist or Freigrenze)
  - Capital gains rates: 0%/15%/20% for long-term, ordinary income for short-term
  - Reports: Form 8949, Schedule D, TurboTax CSV, Income Report

References:
  - IRS Publication 544 (Sales and Other Dispositions of Assets)
  - IRS Form 8949 instructions
  - Rev. Rul. 2019-24 (crypto as property)
  - Notice 2014-21 (crypto taxation guidance)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from src.tax.base import TaxModule
from src.tax.citations import CitationCode, get_citation
from src.tax.models import (
    Exemption,
    HoldingPeriod,
    IncomeCategory,
    ReportFile,
    TaxSummary,
)


class USTaxModule(TaxModule):
    """United States IRS tax rules for cryptocurrency."""

    country_code = "US"
    country_name = "United States"
    currency_code = "USD"

    # ── Cost basis methods ─────────────────────────────────────────────

    def get_cost_basis_methods(self) -> list[str]:
        return ["FIFO", "LIFO", "HIFO"]

    def get_default_method(self) -> str:
        return "FIFO"

    # ── Holding period ─────────────────────────────────────────────────

    def classify_holding_period(
        self, acquired: date, disposed: date
    ) -> HoldingPeriod:
        """
        IRS rule: property held more than one year is long-term.
        <366 days = short-term, >=366 days = long-term.
        """
        days_held = (disposed - acquired).days
        if days_held >= 366:
            return HoldingPeriod.LONG_TERM
        return HoldingPeriod.SHORT_TERM

    # ── Exemptions ─────────────────────────────────────────────────────

    def get_exemptions(self, disposals: list, year: int) -> list[Exemption]:
        """US has no crypto-specific exemptions. Returns empty list."""
        return []

    # ── Tax liability ──────────────────────────────────────────────────

    def calculate_liability(
        self,
        gains: Decimal,
        income: Decimal,
        user_bracket: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Estimate US tax liability on crypto gains + income.

        This is a simplified estimate. Real US taxes depend on filing status,
        other income, deductions, etc. We use single-filer 2025 brackets
        as a reasonable default.

        Long-term capital gains rates (2025, single filer):
          0% up to $48,350
          15% from $48,351 to $533,400
          20% above $533,400

        Short-term gains are taxed as ordinary income.

        Args:
            gains: net taxable capital gains (short + long combined for simplicity)
            income: ordinary income from staking, airdrops, etc.
            user_bracket: optional override for marginal tax rate (e.g. Decimal("0.37"))
        """
        if user_bracket is not None:
            # User-provided marginal rate
            total_taxable = gains + income
            if total_taxable <= Decimal("0"):
                return Decimal("0")
            return (total_taxable * user_bracket).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        # Default estimate: assume all gains are long-term at 15% and
        # income at 24% (median bracket). This is intentionally simplified.
        lt_rate = Decimal("0.15")
        st_rate = Decimal("0.24")

        gains_tax = max(gains, Decimal("0")) * lt_rate
        income_tax = max(income, Decimal("0")) * st_rate
        total = gains_tax + income_tax

        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ── Citation tagging ─────────────────────────────────────────────

    def tag_citations(self, disposals: list) -> None:
        """
        Tag each disposal with the appropriate US tax citation.

        Mutates disposals in-place by setting citation_code, citation_text,
        citation_source, and is_gray_area.
        """
        for d in disposals:
            # Determine holding period classification
            hp = getattr(d, "holding_period", None)
            hp_enum = getattr(d, "holding_period_enum", None)

            is_long = False
            if hp_enum == HoldingPeriod.LONG_TERM:
                is_long = True
            elif isinstance(hp, str) and hp in ("long-term", "long", "LONG_TERM"):
                is_long = True

            # Check for bridge transfers
            source = getattr(d, "source", None) or ""
            tx_type = getattr(d, "tx_type", None) or ""
            if source == "bridge" or tx_type == "bridge":
                citation = get_citation(CitationCode.US_BRIDGE_TRANSFER)
                d.citation_code = CitationCode.US_BRIDGE_TRANSFER.value
                d.citation_text = citation["text"]
                d.citation_source = citation["source"]
                d.is_gray_area = citation["is_gray_area"]
                continue

            if is_long:
                citation = get_citation(CitationCode.US_LONG_TERM_GAIN)
                d.citation_code = CitationCode.US_LONG_TERM_GAIN.value
            else:
                citation = get_citation(CitationCode.US_SHORT_TERM_GAIN)
                d.citation_code = CitationCode.US_SHORT_TERM_GAIN.value

            d.citation_text = citation["text"]
            d.citation_source = citation["source"]
            d.is_gray_area = citation["is_gray_area"]

    def tag_income_citations(self, income_events: list) -> None:
        """
        Tag income events with appropriate US tax citations.

        Mutates income_events in-place.
        """
        for event in income_events:
            tx_type = event.get("tx_type", "") if isinstance(event, dict) else getattr(event, "tx_type", "")

            if tx_type in ("reward", "staking", "stake_reward"):
                citation = get_citation(CitationCode.US_STAKING_INCOME)
                code = CitationCode.US_STAKING_INCOME.value
            elif tx_type in ("mining", "mine"):
                citation = get_citation(CitationCode.US_MINING_INCOME)
                code = CitationCode.US_MINING_INCOME.value
            elif tx_type in ("airdrop",):
                citation = get_citation(CitationCode.US_AIRDROP_INCOME)
                code = CitationCode.US_AIRDROP_INCOME.value
            else:
                continue

            if isinstance(event, dict):
                event["citation_code"] = code
                event["citation_text"] = citation["text"]
                event["citation_source"] = citation["source"]
                event["is_gray_area"] = citation["is_gray_area"]
            else:
                event.citation_code = code
                event.citation_text = citation["text"]
                event.citation_source = citation["source"]
                event.is_gray_area = citation["is_gray_area"]

    # ── Reports ────────────────────────────────────────────────────────

    def generate_reports(
        self,
        disposals: list,
        income_events: list,
        year: int,
        method: str,
    ) -> list[ReportFile]:
        """
        Generate all US tax reports.

        Returns Form 8949 CSV, Schedule D text, TurboTax CSV, and Income CSV.
        """
        # Tag all disposals and income events with citations
        self.tag_citations(disposals)
        self.tag_income_citations(income_events)

        from src.tax.us.form_8949 import generate_form_8949_csv
        from src.tax.us.schedule_d import generate_schedule_d_text
        from src.tax.us.turbotax_export import generate_turbotax_csv
        from src.tax.us.income_report import generate_income_csv

        reports: list[ReportFile] = []

        # Form 8949
        f8949_csv = generate_form_8949_csv(disposals, year, method)
        reports.append(ReportFile(
            filename=f"form8949_{year}_{method}.csv",
            content=f8949_csv,
            mime_type="text/csv",
            report_type="form_8949",
        ))

        # Schedule D
        sched_d_text = generate_schedule_d_text(disposals, year, method)
        reports.append(ReportFile(
            filename=f"schedule_d_{year}_{method}.txt",
            content=sched_d_text,
            mime_type="text/plain",
            report_type="schedule_d",
        ))

        # TurboTax CSV
        turbotax_csv = generate_turbotax_csv(disposals, year, method)
        reports.append(ReportFile(
            filename=f"turbotax_{year}_{method}.csv",
            content=turbotax_csv,
            mime_type="text/csv",
            report_type="turbotax",
        ))

        # Income report
        income_csv = generate_income_csv(income_events, year)
        reports.append(ReportFile(
            filename=f"income_report_{year}.csv",
            content=income_csv,
            mime_type="text/csv",
            report_type="income",
        ))

        return reports

    # ── Currency formatting ────────────────────────────────────────────

    def format_currency(self, amount: Decimal) -> str:
        """Format as USD: $1,234.56"""
        abs_amount = abs(amount)
        formatted = f"${abs_amount:,.2f}"
        if amount < 0:
            formatted = f"-{formatted}"
        return formatted

    # ── Income categories ──────────────────────────────────────────────

    def get_income_categories(self) -> list[IncomeCategory]:
        return [
            IncomeCategory(
                name="Staking Rewards",
                description="Rewards received for staking/validating",
                citation="IRC §61; Rev. Rul. 2023-14",
            ),
            IncomeCategory(
                name="Airdrops",
                description="Tokens received via airdrop",
                citation="Rev. Rul. 2019-24",
            ),
            IncomeCategory(
                name="Mining Income",
                description="Income from mining or validating blocks",
                citation="Notice 2014-21, Q-8",
            ),
            IncomeCategory(
                name="DeFi Interest",
                description="Interest earned from DeFi lending",
                citation="IRC §61(a)(4)",
            ),
        ]
