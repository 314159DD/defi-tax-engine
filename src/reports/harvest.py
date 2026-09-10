"""
Tax loss harvesting - unrealized position analysis and harvest suggestions.

Strategy:
  1. Find open tax lots with current market value < cost basis (unrealized losses)
  2. Calculate potential tax savings based on holding period and estimated tax rate
  3. Warn about wash sale rule (IRS 30-day window before/after sale)
  4. Sort suggestions by potential savings (highest first)
  5. Provide full unrealized position view for dashboard (Sprint 5.1)

IMPORTANT: IRS has NOT definitively ruled on crypto wash sales as of 2026.
We warn users but do not enforce. The 30-day rule may apply in future guidance.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from src.storage.database import Database, TaxLotRepository, DisposalRepository
from src.tax.models import HoldingPeriod

# Estimated marginal tax rates - user should override with actual rates
_SHORT_TERM_RATE = Decimal("0.37")   # max ordinary income rate
_LONG_TERM_RATE = Decimal("0.20")    # max LTCG rate (+ 3.8% NIIT for high earners)

_LONG_TERM_DAYS = 365

# German Spekulationsfrist: >365 days = tax-free
_SPEKULATIONSFRIST_DAYS = 365


# ---------------------------------------------------------------------------
# UnrealizedPosition - real-time dashboard view
# ---------------------------------------------------------------------------

@dataclass
class UnrealizedPosition:
    """
    A single unrealized position derived from open tax lots.

    Used by the harvest dashboard to show current P&L per lot.
    """
    token: str
    lot_id: str
    amount: Decimal
    cost_basis: Decimal
    current_value: Decimal
    unrealized_gain_loss: Decimal
    holding_period: HoldingPeriod
    acquisition_date: date
    days_held: int
    # DE-specific fields
    spekulationsfrist_remaining: Optional[int] = None
    is_tax_free: bool = False

    def as_dict(self) -> dict:
        return {
            "token": self.token,
            "lot_id": self.lot_id,
            "amount": str(self.amount),
            "cost_basis": str(self.cost_basis),
            "current_value": str(self.current_value),
            "unrealized_gain_loss": str(self.unrealized_gain_loss),
            "holding_period": self.holding_period.value,
            "acquisition_date": str(self.acquisition_date),
            "days_held": self.days_held,
            "spekulationsfrist_remaining": self.spekulationsfrist_remaining,
            "is_tax_free": self.is_tax_free,
        }


def get_unrealized_positions(
    tax_lots: list[dict],
    current_prices: dict[str, Decimal],
    country: str = "US",
    as_of_date: Optional[date] = None,
) -> list[UnrealizedPosition]:
    """
    Build unrealized position list from open tax lots and current prices.

    Args:
        tax_lots: list of lot dicts from TaxLotRepository.get_all()
            Each has: id, token, amount, cost_basis_usd, acquisition_date, remaining
        current_prices: token_symbol (upper) -> current USD/EUR price
        country: "US" or "DE" - affects holding period classification
        as_of_date: date to calculate from (default: today)

    Returns:
        List of UnrealizedPosition sorted by unrealized_gain_loss ascending
        (largest losses first - best harvest candidates).
    """
    today = as_of_date or date.today()
    positions: list[UnrealizedPosition] = []

    for lot in tax_lots:
        remaining = lot["remaining"]
        if remaining <= Decimal("0"):
            continue

        token = lot["token"].upper()
        current_price = current_prices.get(token)
        if current_price is None:
            continue

        amount = lot["amount"]
        if amount <= Decimal("0"):
            continue

        cost_per_unit = lot["cost_basis_usd"] / amount
        cost_of_remaining = remaining * cost_per_unit
        current_value = remaining * current_price
        unrealized = current_value - cost_of_remaining

        # Parse acquisition date
        acq_date_str = str(lot["acquisition_date"])[:10]
        try:
            acq_date = date.fromisoformat(acq_date_str)
        except ValueError:
            continue

        days_held = (today - acq_date).days

        # Holding period classification depends on country
        if country == "DE":
            if days_held > _SPEKULATIONSFRIST_DAYS:
                hp = HoldingPeriod.EXEMPT
            else:
                hp = HoldingPeriod.SHORT_TERM
        else:
            # US rules
            if days_held >= 366:
                hp = HoldingPeriod.LONG_TERM
            else:
                hp = HoldingPeriod.SHORT_TERM

        # DE-specific: Spekulationsfrist remaining days
        spek_remaining: Optional[int] = None
        is_tax_free = False
        if country == "DE":
            spek_end_days = _SPEKULATIONSFRIST_DAYS + 1 - days_held
            spek_remaining = max(spek_end_days, 0)
            is_tax_free = spek_remaining == 0

        positions.append(UnrealizedPosition(
            token=token,
            lot_id=lot["id"],
            amount=remaining,
            cost_basis=cost_of_remaining,
            current_value=current_value,
            unrealized_gain_loss=unrealized,
            holding_period=hp,
            acquisition_date=acq_date,
            days_held=days_held,
            spekulationsfrist_remaining=spek_remaining,
            is_tax_free=is_tax_free,
        ))

    # Sort by unrealized gain/loss ascending (largest losses first)
    positions.sort(key=lambda p: p.unrealized_gain_loss)
    return positions


# ---------------------------------------------------------------------------
# HarvestSuggestion (original, kept for backward compatibility)
# ---------------------------------------------------------------------------

@dataclass
class HarvestSuggestion:
    token: str
    lot_id: str
    amount_remaining: Decimal
    cost_basis_per_unit: Decimal
    current_price_usd: Decimal        # must be provided externally (real-time price)
    unrealized_loss_usd: Decimal      # negative = loss
    holding_period: str               # "short" | "long"
    potential_tax_savings: Decimal    # positive = savings
    wash_sale_warning: bool           # True if a recent purchase exists within 30 days
    acquisition_date: str             # ISO date
    days_held: int

    def as_dict(self) -> dict:
        return {
            "token": self.token,
            "lot_id": self.lot_id,
            "amount_remaining": str(self.amount_remaining),
            "cost_basis_per_unit": str(self.cost_basis_per_unit),
            "current_price_usd": str(self.current_price_usd),
            "unrealized_loss_usd": str(self.unrealized_loss_usd),
            "holding_period": self.holding_period,
            "potential_tax_savings": str(self.potential_tax_savings),
            "wash_sale_warning": self.wash_sale_warning,
            "acquisition_date": self.acquisition_date,
            "days_held": self.days_held,
        }


class HarvestAnalyzer:
    """Identifies tax loss harvesting opportunities from open lots."""

    def __init__(self, db: Database) -> None:
        self._lot_repo = TaxLotRepository(db)
        self._db = db

    def get_positions(
        self,
        current_prices: dict[str, Decimal],
        country: str = "US",
        as_of_date: Optional[date] = None,
    ) -> list[UnrealizedPosition]:
        """
        Return all unrealized positions (gains AND losses) for the dashboard.
        """
        all_lots = self._lot_repo.get_all()
        return get_unrealized_positions(all_lots, current_prices, country, as_of_date)

    def analyze(
        self,
        current_prices: dict[str, Decimal],
        short_term_rate: Decimal = _SHORT_TERM_RATE,
        long_term_rate: Decimal = _LONG_TERM_RATE,
        as_of_date: Optional[datetime] = None,
    ) -> list[HarvestSuggestion]:
        """
        Return harvest suggestions sorted by potential_tax_savings (descending).

        current_prices: token_symbol (upper) -> current USD price
        """
        as_of = as_of_date or datetime.now(timezone.utc)
        all_lots = self._lot_repo.get_all()

        # Build a set of recent disposal/purchase dates per token for wash sale check
        recent_purchases = self._recent_purchases_by_token(as_of)

        suggestions: list[HarvestSuggestion] = []

        for lot in all_lots:
            remaining = lot["remaining"]
            if remaining <= Decimal("0"):
                continue

            token = lot["token"].upper()
            current_price = current_prices.get(token)
            if current_price is None:
                continue  # can't calculate without price

            cost_basis_total = lot["cost_basis_usd"]
            amount = lot["amount"]
            if amount <= Decimal("0"):
                continue

            cost_per_unit = cost_basis_total / amount
            current_value = remaining * current_price
            cost_of_remaining = remaining * cost_per_unit
            unrealized = current_value - cost_of_remaining

            if unrealized >= Decimal("0"):
                continue  # skip gains - only interested in losses

            # Holding period
            acq_date_str = lot["acquisition_date"][:10]
            try:
                acq_dt = datetime.fromisoformat(acq_date_str).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            days_held = (as_of - acq_dt).days
            holding_period = "long" if days_held >= _LONG_TERM_DAYS else "short"

            rate = long_term_rate if holding_period == "long" else short_term_rate
            potential_savings = abs(unrealized) * rate

            # Wash sale: warn if same token purchased within 30 days before/after
            wash_warning = self._check_wash_sale(token, as_of, recent_purchases)

            suggestions.append(HarvestSuggestion(
                token=token,
                lot_id=lot["id"],
                amount_remaining=remaining,
                cost_basis_per_unit=cost_per_unit,
                current_price_usd=current_price,
                unrealized_loss_usd=unrealized,
                holding_period=holding_period,
                potential_tax_savings=potential_savings,
                wash_sale_warning=wash_warning,
                acquisition_date=acq_date_str,
                days_held=days_held,
            ))

        # Sort by potential savings descending (harvest the biggest savings first)
        suggestions.sort(key=lambda s: s.potential_tax_savings, reverse=True)
        return suggestions

    def _recent_purchases_by_token(self, as_of: datetime) -> dict[str, list[datetime]]:
        """Return map of token -> [purchase dates] within the last 30 days."""
        window_start = as_of - timedelta(days=30)
        result: dict[str, list[datetime]] = {}

        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT tx_type, timestamp, raw_json
                FROM transactions
                WHERE tx_type IN ('swap','transfer','lp_remove')
                  AND timestamp >= ?
                ORDER BY timestamp
                """,
                (window_start.isoformat(),),
            ).fetchall()

        for row in rows:
            raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
            for asset in raw.get("assets_in", []):
                token = asset.get("token_symbol", "").upper()
                if token:
                    try:
                        dt = datetime.fromisoformat(row["timestamp"]).replace(tzinfo=timezone.utc)
                        result.setdefault(token, []).append(dt)
                    except ValueError:
                        pass

        return result

    def _check_wash_sale(
        self,
        token: str,
        sell_date: datetime,
        recent_purchases: dict[str, list[datetime]],
    ) -> bool:
        """
        Wash sale warning: was this token purchased within 30 days before/after sell_date?
        """
        dates = recent_purchases.get(token, [])
        for d in dates:
            if abs((d - sell_date).days) <= 30:
                return True
        return False

    def print_report(
        self,
        current_prices: dict[str, Decimal],
        short_term_rate: Decimal = _SHORT_TERM_RATE,
        long_term_rate: Decimal = _LONG_TERM_RATE,
    ) -> str:
        suggestions = self.analyze(current_prices, short_term_rate, long_term_rate)

        if not suggestions:
            return "No tax loss harvesting opportunities found."

        lines = [
            "Tax Loss Harvesting Suggestions",
            "=" * 60,
            f"(Rates used: ST={short_term_rate:.0%}, LT={long_term_rate:.0%})",
            "",
        ]

        for i, s in enumerate(suggestions, 1):
            wash = " ⚠ WASH SALE RISK" if s.wash_sale_warning else ""
            lines += [
                f"{i}. {s.token} - {s.holding_period.title()}-Term{wash}",
                f"   Lot acquired: {s.acquisition_date} ({s.days_held} days held)",
                f"   Amount:        {s.amount_remaining:.8f} {s.token}".rstrip("0").rstrip(".") + f" {s.token}",
                f"   Cost basis/unit: ${s.cost_basis_per_unit:.4f}",
                f"   Current price:   ${s.current_price_usd:.4f}",
                f"   Unrealized loss: ${s.unrealized_loss_usd:.2f}",
                f"   Potential savings: ${s.potential_tax_savings:.2f}",
                "",
            ]

        if any(s.wash_sale_warning for s in suggestions):
            lines += [
                "⚠  WASH SALE WARNING: IRS has not definitively ruled on crypto wash sales.",
                "   Selling and rebuying the same asset within 30 days may disallow the loss.",
                "   Consult a tax professional before harvesting flagged positions.",
            ]

        return "\n".join(lines)
