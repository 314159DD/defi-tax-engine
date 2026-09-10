"""
Abstract base class for country-specific tax modules.

Each country module implements the rules for:
  - cost basis methods available
  - holding period classification
  - exemptions (e.g. German Spekulationsfrist, Freigrenze)
  - tax liability calculation from brackets
  - report generation (IRS forms, Anlage SO, WISO, etc.)
  - currency formatting
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Optional

from src.tax.models import (
    Exemption,
    HoldingPeriod,
    IncomeCategory,
    ReportFile,
    TaxSummary,
)


class TaxModule(ABC):
    """
    Abstract interface that every country tax module must implement.

    Subclass this for US, DE, AT, CH, UK, AU, etc.
    """

    country_code: str       # ISO 3166-1 alpha-2: "US", "DE", etc.
    country_name: str       # "United States", "Germany", etc.
    currency_code: str      # ISO 4217: "USD", "EUR", etc.

    # ── Cost basis methods ─────────────────────────────────────────────

    @abstractmethod
    def get_cost_basis_methods(self) -> list[str]:
        """Return list of cost basis methods available for filing (e.g. ["FIFO"])."""
        ...

    @abstractmethod
    def get_default_method(self) -> str:
        """Return the default/recommended method for this country."""
        ...

    # ── Holding period classification ──────────────────────────────────

    @abstractmethod
    def classify_holding_period(
        self, acquired: date, disposed: date
    ) -> HoldingPeriod:
        """
        Classify the holding period for a single disposal.

        Args:
            acquired: date the asset was acquired
            disposed: date the asset was disposed

        Returns:
            HoldingPeriod enum value (SHORT_TERM, LONG_TERM, or EXEMPT)
        """
        ...

    # ── Exemptions ─────────────────────────────────────────────────────

    @abstractmethod
    def get_exemptions(
        self, disposals: list, year: int
    ) -> list[Exemption]:
        """
        Analyze disposals and return exemptions that apply.

        Args:
            disposals: list of Disposal objects for the year
            year: tax year

        Returns:
            list of Exemption objects referencing specific disposals
        """
        ...

    # ── Tax liability ──────────────────────────────────────────────────

    @abstractmethod
    def calculate_liability(
        self,
        gains: Decimal,
        income: Decimal,
        user_bracket: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate estimated tax liability.

        Args:
            gains: net taxable capital gains for the year
            income: total ordinary income (staking, airdrops, etc.)
            user_bracket: optional user-provided marginal tax rate override

        Returns:
            estimated tax amount as Decimal
        """
        ...

    # ── Report generation ──────────────────────────────────────────────

    @abstractmethod
    def generate_reports(
        self,
        disposals: list,
        income_events: list,
        year: int,
        method: str,
    ) -> list[ReportFile]:
        """
        Generate all tax reports for this country.

        Args:
            disposals: list of Disposal objects
            income_events: list of income event dicts
            year: tax year
            method: cost basis method used

        Returns:
            list of ReportFile objects ready for download
        """
        ...

    # ── Currency formatting ────────────────────────────────────────────

    @abstractmethod
    def format_currency(self, amount: Decimal) -> str:
        """
        Format a monetary amount for display in this country's convention.

        Examples:
            US: "$1,234.56"
            DE: "1.234,56 EUR"
        """
        ...

    # ── Income categories ──────────────────────────────────────────────

    def get_income_categories(self) -> list[IncomeCategory]:
        """
        Return income categories relevant for this jurisdiction.

        Override in subclass for country-specific categories.
        Default returns common crypto income types.
        """
        return [
            IncomeCategory(
                name="Staking Rewards",
                description="Rewards received for staking crypto assets",
                citation="",
            ),
            IncomeCategory(
                name="Airdrops",
                description="Tokens received via airdrop",
                citation="",
            ),
            IncomeCategory(
                name="Mining Income",
                description="Income from mining or validating",
                citation="",
            ),
            IncomeCategory(
                name="DeFi Interest",
                description="Interest earned from DeFi lending protocols",
                citation="",
            ),
        ]
