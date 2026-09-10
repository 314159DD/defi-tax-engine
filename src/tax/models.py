"""
Shared types for the country-specific tax module system.

All monetary values use Decimal - NEVER float.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


class HoldingPeriod(str, Enum):
    """Classification of how long an asset was held before disposal."""
    SHORT_TERM = "short-term"
    LONG_TERM = "long-term"
    EXEMPT = "exempt"  # e.g. German Spekulationsfrist (>1 year = tax-free)


@dataclass
class Exemption:
    """
    A tax exemption applied to a specific disposal.

    Used by country modules to tag disposals that are partially or fully
    exempt from taxation (e.g. German Freigrenze, Spekulationsfrist).
    """
    disposal_id: str           # references Disposal via tx_hash or synthetic ID
    reason: str                # human-readable reason
    citation_code: str         # e.g. "§23 Abs. 1 EStG"
    citation_text: str         # full citation text
    exempt_amount: Decimal = Decimal("0")  # amount of gain/loss that is exempt

    def __post_init__(self) -> None:
        if not isinstance(self.exempt_amount, Decimal):
            raise TypeError(f"Exemption.exempt_amount must be Decimal, got {type(self.exempt_amount)}")


@dataclass
class TaxSummary:
    """
    Aggregated tax calculation result for a given year + country.
    """
    total_gains: Decimal = Decimal("0")
    total_losses: Decimal = Decimal("0")
    net: Decimal = Decimal("0")
    short_term_gains: Decimal = Decimal("0")
    long_term_gains: Decimal = Decimal("0")
    exempt_gains: Decimal = Decimal("0")
    tax_liability: Decimal = Decimal("0")
    exemptions: list[Exemption] = field(default_factory=list)
    income_total: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for attr in (
            "total_gains", "total_losses", "net", "short_term_gains",
            "long_term_gains", "exempt_gains", "tax_liability", "income_total",
        ):
            v = getattr(self, attr)
            if not isinstance(v, Decimal):
                raise TypeError(f"TaxSummary.{attr} must be Decimal, got {type(v)}")

    def as_dict(self) -> dict:
        return {
            "total_gains": str(self.total_gains),
            "total_losses": str(self.total_losses),
            "net": str(self.net),
            "short_term_gains": str(self.short_term_gains),
            "long_term_gains": str(self.long_term_gains),
            "exempt_gains": str(self.exempt_gains),
            "tax_liability": str(self.tax_liability),
            "income_total": str(self.income_total),
            "exemption_count": len(self.exemptions),
        }


@dataclass
class ReportFile:
    """
    A generated report file ready for download.
    """
    filename: str
    content: bytes | str
    mime_type: str
    report_type: str  # e.g. "form_8949", "anlage_so", "wiso", "datev"

    @property
    def content_bytes(self) -> bytes:
        if isinstance(self.content, str):
            return self.content.encode("utf-8")
        return self.content


@dataclass
class IncomeCategory:
    """
    Describes a category of taxable income and its legal basis.
    """
    name: str           # e.g. "Staking Rewards"
    description: str    # e.g. "Rewards received for staking crypto assets"
    citation: str       # e.g. "IRC §61" or "§22 Nr. 3 EStG"
