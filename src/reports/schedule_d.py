"""
IRS Schedule D summary generator.

Schedule D aggregates the totals from Form 8949:
  - Part I:  Short-term capital gains/losses
  - Part II: Long-term capital gains/losses
  - Part III: Net capital gain/loss + carryover calculation

Capital loss carryover rules (simplified):
  - Net capital loss limited to $3,000/year deduction against ordinary income
  - Excess carries over indefinitely to future years
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.reports.form_8949 import Form8949Generator
from src.storage.database import Database

_MAX_DEDUCTIBLE_LOSS = Decimal("-3000")  # IRS annual cap


@dataclass
class ScheduleDLine:
    description: str
    proceeds: Decimal
    cost_basis: Decimal
    gain_loss: Decimal


@dataclass
class ScheduleDSummary:
    year: int
    method: str
    # Part I - short-term
    short_term_proceeds: Decimal
    short_term_cost_basis: Decimal
    short_term_net: Decimal           # net short-term gain/loss
    # Part II - long-term
    long_term_proceeds: Decimal
    long_term_cost_basis: Decimal
    long_term_net: Decimal            # net long-term gain/loss
    # Part III
    net_capital_gain_loss: Decimal    # short + long
    deductible_loss: Decimal          # max $3,000 if net loss
    carryover_loss: Decimal           # amount beyond $3,000 cap

    def as_dict(self) -> dict:
        return {
            "year": self.year,
            "method": self.method,
            "short_term": {
                "proceeds": str(self.short_term_proceeds),
                "cost_basis": str(self.short_term_cost_basis),
                "net": str(self.short_term_net),
            },
            "long_term": {
                "proceeds": str(self.long_term_proceeds),
                "cost_basis": str(self.long_term_cost_basis),
                "net": str(self.long_term_net),
            },
            "net_capital_gain_loss": str(self.net_capital_gain_loss),
            "deductible_loss": str(self.deductible_loss),
            "carryover_loss": str(self.carryover_loss),
        }


class ScheduleDGenerator:
    """Generates Schedule D from Form 8949 totals."""

    def __init__(self, db: Database) -> None:
        self._form8949 = Form8949Generator(db)

    def generate(
        self,
        year: int,
        method: str = "FIFO",
        prior_year_carryover: Decimal = Decimal("0"),
    ) -> ScheduleDSummary:
        """
        Compute Schedule D totals.

        prior_year_carryover: any capital loss carried over from previous years
        (positive number representing the unused loss amount).
        """
        summary = self._form8949.summary(year, method)

        short = summary["part_i_short_term"]
        long_ = summary["part_ii_long_term"]

        st_proceeds = short["proceeds"]
        st_basis = short["cost_basis"]
        st_net = short["gain_loss"]

        lt_proceeds = long_["proceeds"]
        lt_basis = long_["cost_basis"]
        lt_net = long_["gain_loss"]

        # Apply prior year carryover (reduces gains or increases loss)
        # Carryover short-term losses reduce short-term first
        if prior_year_carryover > Decimal("0"):
            st_net -= prior_year_carryover

        net = st_net + lt_net

        # Deductible loss and carryover calculation
        if net < Decimal("0"):
            deductible = max(net, _MAX_DEDUCTIBLE_LOSS)
            carryover = net - deductible  # this is negative; abs is the carryover
            carryover = abs(carryover)
        else:
            deductible = Decimal("0")
            carryover = Decimal("0")

        return ScheduleDSummary(
            year=year,
            method=method,
            short_term_proceeds=st_proceeds,
            short_term_cost_basis=st_basis,
            short_term_net=st_net,
            long_term_proceeds=lt_proceeds,
            long_term_cost_basis=lt_basis,
            long_term_net=lt_net,
            net_capital_gain_loss=net,
            deductible_loss=deductible,
            carryover_loss=carryover,
        )

    def print_report(
        self,
        year: int,
        method: str = "FIFO",
        prior_year_carryover: Decimal = Decimal("0"),
    ) -> str:
        s = self.generate(year, method, prior_year_carryover)
        lines = [
            f"Schedule D - Capital Gains and Losses ({year}, {method})",
            "=" * 60,
            "",
            "PART I - Short-Term Capital Gains and Losses",
            f"  Proceeds:    ${s.short_term_proceeds:>14,.2f}",
            f"  Cost Basis:  ${s.short_term_cost_basis:>14,.2f}",
            f"  Net:         ${s.short_term_net:>14,.2f}",
            "",
            "PART II - Long-Term Capital Gains and Losses",
            f"  Proceeds:    ${s.long_term_proceeds:>14,.2f}",
            f"  Cost Basis:  ${s.long_term_cost_basis:>14,.2f}",
            f"  Net:         ${s.long_term_net:>14,.2f}",
            "",
            "PART III - Summary",
            f"  Net Capital Gain/(Loss):  ${s.net_capital_gain_loss:>12,.2f}",
        ]
        if s.net_capital_gain_loss < Decimal("0"):
            lines += [
                f"  Deductible Loss (max $3k): ${s.deductible_loss:>12,.2f}",
                f"  Carryover to Next Year:   ${s.carryover_loss:>12,.2f}",
            ]
        return "\n".join(lines)
