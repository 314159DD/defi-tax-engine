"""
IRS Schedule D summary generator - standalone functions for tax module system.

Adapted from src/reports/schedule_d.py to work with Disposal objects directly.

Schedule D aggregates the totals from Form 8949:
  - Part I:  Short-term capital gains/losses
  - Part II: Long-term capital gains/losses
  - Part III: Net capital gain/loss + carryover calculation

Capital loss carryover rules:
  - Net capital loss limited to $3,000/year deduction against ordinary income
  - Excess carries over indefinitely to future years
"""
from __future__ import annotations

from decimal import Decimal

from src.tax.models import HoldingPeriod

_MAX_DEDUCTIBLE_LOSS = Decimal("-3000")  # IRS annual cap


def _is_short_term(d) -> bool:
    """Check if a disposal is short-term."""
    hp = d.holding_period
    if isinstance(hp, HoldingPeriod):
        return hp == HoldingPeriod.SHORT_TERM
    return str(hp) in ("short-term", "short", "SHORT_TERM")


def generate_schedule_d_text(
    disposals: list,
    year: int,
    method: str,
    prior_year_carryover: Decimal = Decimal("0"),
) -> str:
    """
    Generate Schedule D summary as a text report.

    Args:
        disposals: list of Disposal dataclass instances
        year: tax year
        method: cost basis method used
        prior_year_carryover: unused loss from prior years (positive number)

    Returns:
        Human-readable Schedule D text
    """
    # Filter to the correct year
    year_disposals = []
    for d in disposals:
        if hasattr(d.date, "year") and d.date.year == year:
            year_disposals.append(d)

    # Compute totals
    st_proceeds = Decimal("0")
    st_basis = Decimal("0")
    st_net = Decimal("0")
    lt_proceeds = Decimal("0")
    lt_basis = Decimal("0")
    lt_net = Decimal("0")

    for d in year_disposals:
        if _is_short_term(d):
            st_proceeds += d.proceeds_usd
            st_basis += d.cost_basis_usd
            st_net += d.gain_loss_usd
        else:
            lt_proceeds += d.proceeds_usd
            lt_basis += d.cost_basis_usd
            lt_net += d.gain_loss_usd

    # Apply prior year carryover
    if prior_year_carryover > Decimal("0"):
        st_net -= prior_year_carryover

    net = st_net + lt_net

    # Deductible loss and carryover
    if net < Decimal("0"):
        deductible = max(net, _MAX_DEDUCTIBLE_LOSS)
        carryover = abs(net - deductible)
    else:
        deductible = Decimal("0")
        carryover = Decimal("0")

    lines = [
        f"Schedule D \u2014 Capital Gains and Losses ({year}, {method})",
        "=" * 60,
        "",
        "PART I \u2014 Short-Term Capital Gains and Losses",
        f"  Proceeds:    ${st_proceeds:>14,.2f}",
        f"  Cost Basis:  ${st_basis:>14,.2f}",
        f"  Net:         ${st_net:>14,.2f}",
        "",
        "PART II \u2014 Long-Term Capital Gains and Losses",
        f"  Proceeds:    ${lt_proceeds:>14,.2f}",
        f"  Cost Basis:  ${lt_basis:>14,.2f}",
        f"  Net:         ${lt_net:>14,.2f}",
        "",
        "PART III \u2014 Summary",
        f"  Net Capital Gain/(Loss):  ${net:>12,.2f}",
    ]
    if net < Decimal("0"):
        lines += [
            f"  Deductible Loss (max $3k): ${deductible:>12,.2f}",
            f"  Carryover to Next Year:   ${carryover:>12,.2f}",
        ]

    return "\n".join(lines)
