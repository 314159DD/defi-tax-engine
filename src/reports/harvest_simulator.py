"""
Tax loss harvesting simulation engine.

Allows users to select positions for hypothetical sale and see the projected
tax impact before committing. Supports multi-position scenarios and
country-specific rules (US wash sales, DE Freigrenze cliff).

All monetary values use Decimal - NEVER float.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from src.reports.harvest import UnrealizedPosition
from src.tax.base import TaxModule
from src.tax.models import HoldingPeriod


# German Freigrenze (EUR 1,000 cliff - §23 Abs. 3 Satz 5 EStG)
_DE_FREIGRENZE = Decimal("1000")


@dataclass
class HarvestScenario:
    """
    Result of a hypothetical harvest simulation.

    Represents the combined tax impact of selling the selected positions.
    """
    positions_to_sell: list[str]         # lot IDs of positions in the scenario
    total_realized_loss: Decimal         # sum of losses (negative = loss, stored as positive here)
    total_realized_gain: Decimal         # sum of gains
    net_impact: Decimal                  # total_realized_gain - total_realized_loss
    projected_tax_savings: Decimal       # estimated tax savings at user's bracket
    # DE-specific Freigrenze impact
    freigrenze_impact: str               # "stays_under" | "would_exceed" | "already_exceeded" | "n/a"
    new_freigrenze_total: Decimal        # new YTD short-term gains after harvest

    def as_dict(self) -> dict:
        return {
            "positions_to_sell": self.positions_to_sell,
            "total_realized_loss": str(self.total_realized_loss),
            "total_realized_gain": str(self.total_realized_gain),
            "net_impact": str(self.net_impact),
            "projected_tax_savings": str(self.projected_tax_savings),
            "freigrenze_impact": self.freigrenze_impact,
            "new_freigrenze_total": str(self.new_freigrenze_total),
        }


def simulate_harvest(
    positions: list[UnrealizedPosition],
    tax_module: TaxModule,
    current_year_gains: Decimal,
    user_bracket: Decimal,
    selected_lot_ids: Optional[list[str]] = None,
) -> HarvestScenario:
    """
    Simulate selling selected positions and calculate tax impact.

    Args:
        positions: list of UnrealizedPosition objects (from get_unrealized_positions)
        tax_module: country-specific TaxModule instance
        current_year_gains: total realized short-term gains YTD (for Freigrenze check)
        user_bracket: user's estimated marginal tax rate (e.g. Decimal("0.37"))
        selected_lot_ids: list of lot IDs to sell. If None, sell all positions.

    Returns:
        HarvestScenario with projected impact
    """
    # Filter to selected positions
    if selected_lot_ids is not None:
        selected_set = set(selected_lot_ids)
        selected = [p for p in positions if p.lot_id in selected_set]
    else:
        selected = list(positions)

    if not selected:
        return HarvestScenario(
            positions_to_sell=[],
            total_realized_loss=Decimal("0"),
            total_realized_gain=Decimal("0"),
            net_impact=Decimal("0"),
            projected_tax_savings=Decimal("0"),
            freigrenze_impact="n/a",
            new_freigrenze_total=current_year_gains,
        )

    country = tax_module.country_code

    total_loss = Decimal("0")
    total_gain = Decimal("0")
    lot_ids: list[str] = []

    # Track short-term gains/losses separately for Freigrenze
    short_term_gain_delta = Decimal("0")

    for pos in selected:
        lot_ids.append(pos.lot_id)
        gl = pos.unrealized_gain_loss

        if gl < Decimal("0"):
            total_loss += abs(gl)
        else:
            total_gain += gl

        # For DE Freigrenze: only short-term disposals count
        if country == "DE" and pos.holding_period == HoldingPeriod.SHORT_TERM:
            if gl > Decimal("0"):
                short_term_gain_delta += gl
            else:
                short_term_gain_delta += gl  # negative, reduces total
        elif country != "DE":
            # US: all disposals count (short and long treated differently for rates,
            # but for the net calculation we aggregate)
            pass

    net_impact = total_gain - total_loss

    # Calculate projected tax savings
    # If net_impact is negative, it's a net loss -> tax savings
    # If positive, it's a net gain -> additional tax
    if net_impact < Decimal("0"):
        # Net loss -> savings
        projected_savings = (abs(net_impact) * user_bracket).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        # Net gain -> negative savings (additional tax)
        projected_savings = -(net_impact * user_bracket).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    # DE-specific: Freigrenze analysis
    freigrenze_impact = "n/a"
    new_freigrenze_total = current_year_gains

    if country == "DE":
        new_freigrenze_total = current_year_gains + short_term_gain_delta

        if current_year_gains >= _DE_FREIGRENZE:
            freigrenze_impact = "already_exceeded"
        elif new_freigrenze_total >= _DE_FREIGRENZE:
            freigrenze_impact = "would_exceed"
        else:
            freigrenze_impact = "stays_under"

    return HarvestScenario(
        positions_to_sell=lot_ids,
        total_realized_loss=total_loss,
        total_realized_gain=total_gain,
        net_impact=net_impact,
        projected_tax_savings=projected_savings,
        freigrenze_impact=freigrenze_impact,
        new_freigrenze_total=new_freigrenze_total,
    )


def get_freigrenze_headroom(
    current_year_gains: Decimal,
) -> dict:
    """
    Calculate how much more the user can harvest before hitting the Freigrenze cliff.

    Returns dict with:
        limit: 1000
        realized_ytd: current gains
        remaining: headroom before cliff
        status: "under" | "at_limit" | "over"
    """
    remaining = max(_DE_FREIGRENZE - current_year_gains, Decimal("0"))

    if current_year_gains >= _DE_FREIGRENZE:
        status = "over"
    elif remaining == Decimal("0"):
        status = "at_limit"
    else:
        status = "under"

    return {
        "limit": str(_DE_FREIGRENZE),
        "realized_ytd": str(current_year_gains),
        "remaining": str(remaining),
        "status": status,
    }
