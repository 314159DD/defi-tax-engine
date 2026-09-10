"""
Tax lot and disposal data models.

CRITICAL: All monetary values use decimal.Decimal - NEVER float.

TaxLot      - an open acquisition position waiting to be consumed
LotConsumption - a partial/full lot used in a disposal
Disposal    - a realized gain/loss event
LotManager  - in-memory lot book used during calculation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from src.tax.models import Exemption, HoldingPeriod


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TaxLot:
    """
    A single acquisition lot.

    cost_per_unit  = cost_basis_usd / amount
    remaining      = amount still available (decreases as consumed)
    """
    id: str                          # UUID from DB or synthetic
    token: str                       # e.g. "ETH", "USDC"
    amount: Decimal                  # original units acquired
    cost_basis_usd: Decimal          # total cost in USD (inc. gas)
    acquisition_date: datetime
    remaining: Decimal               # units not yet disposed
    source: str                      # "swap", "reward", "airdrop", "lp_remove", etc.
    tx_hash: str
    spekulationsfrist_end: Optional[date] = None  # for DE: date when 1-year holding period ends

    @property
    def cost_per_unit(self) -> Decimal:
        if self.amount == Decimal("0"):
            return Decimal("0")
        return self.cost_basis_usd / self.amount

    def __post_init__(self) -> None:
        for attr in ("amount", "cost_basis_usd", "remaining"):
            v = getattr(self, attr)
            if not isinstance(v, Decimal):
                raise TypeError(f"TaxLot.{attr} must be Decimal, got {type(v)}")


@dataclass
class LotConsumption:
    """Records which portion of a lot was consumed in a disposal."""
    lot_id: str
    token: str
    amount_consumed: Decimal
    cost_basis_consumed: Decimal
    acquisition_date: datetime


@dataclass
class Disposal:
    """
    A realized gain/loss event.

    holding_period:  "short-term" (<= 365 days)  or  "long-term" (> 365 days)
    method:          "FIFO", "LIFO", or "HIFO"
    lots_consumed:   which lots (and how much) were consumed

    Citation fields (Sprint 4.3 - Transparent Tax Logic):
        citation_code:   e.g. "US_SHORT_TERM_GAIN", "DE_SPEKULATIONSFRIST_EXEMPT"
        citation_text:   human-readable legal reference
        citation_source: authoritative source (IRC, BMF-Schreiben, etc.)
        is_gray_area:    True if the tax treatment is uncertain/debated
    """
    date: datetime
    token: str
    amount: Decimal
    proceeds_usd: Decimal
    cost_basis_usd: Decimal
    gain_loss_usd: Decimal
    holding_period: str                     # "short-term" | "long-term" | "exempt"
    method: str                             # "FIFO" | "LIFO" | "HIFO"
    lots_consumed: list[LotConsumption]
    tx_hash: str
    exemption: Optional[Exemption] = None   # country-specific exemption (if any)
    holding_period_enum: Optional[HoldingPeriod] = None  # typed enum (from TaxModule)
    # Citation fields - transparent tax logic
    citation_code: Optional[str] = None
    citation_text: Optional[str] = None
    citation_source: Optional[str] = None
    is_gray_area: bool = False

    def __post_init__(self) -> None:
        for attr in ("amount", "proceeds_usd", "cost_basis_usd", "gain_loss_usd"):
            v = getattr(self, attr)
            if not isinstance(v, Decimal):
                raise TypeError(f"Disposal.{attr} must be Decimal, got {type(v)}")


# ---------------------------------------------------------------------------
# Holding period
# ---------------------------------------------------------------------------

_ONE_YEAR = timedelta(days=365)


def holding_period(acquisition_date: datetime, disposal_date: datetime) -> str:
    """Return 'long-term' if held > 1 year, else 'short-term'."""
    if (disposal_date - acquisition_date) > _ONE_YEAR:
        return "long-term"
    return "short-term"


# ---------------------------------------------------------------------------
# LotManager  - in-memory lot book
# ---------------------------------------------------------------------------

class LotManager:
    """
    Manages a per-token collection of open TaxLots.

    Used by the calculator engine as it walks transactions in chronological
    order.  Mutations happen in-memory; the engine is responsible for
    persisting results via the DB repositories.
    """

    def __init__(self) -> None:
        # token → list of TaxLot (insertion order preserved)
        self._lots: dict[str, list[TaxLot]] = {}

    # ── Acquisition ───────────────────────────────────────────────────────

    def add_lot(self, lot: TaxLot) -> None:
        """Add a new acquisition lot for the given token."""
        self._lots.setdefault(lot.token, []).append(lot)

    # ── Query ─────────────────────────────────────────────────────────────

    def open_lots(self, token: str) -> list[TaxLot]:
        """Return lots with remaining > 0 in insertion order."""
        return [lot for lot in self._lots.get(token, []) if lot.remaining > Decimal("0")]

    def total_basis(self, token: str) -> Decimal:
        """Sum of remaining cost basis across all open lots for a token."""
        return sum(
            (lot.remaining * lot.cost_per_unit for lot in self.open_lots(token)),
            Decimal("0"),
        )

    def total_remaining(self, token: str) -> Decimal:
        return sum(
            (lot.remaining for lot in self.open_lots(token)),
            Decimal("0"),
        )

    # ── LP lot helpers ────────────────────────────────────────────────────

    def add_lp_lot(
        self,
        lp_token: str,
        cost_basis_usd: Decimal,
        amount: Decimal,
        acquisition_date: datetime,
        tx_hash: str,
        lot_id: str,
    ) -> None:
        """Record an LP token lot whose cost = sum of tokens deposited."""
        lot = TaxLot(
            id=lot_id,
            token=lp_token,
            amount=amount,
            cost_basis_usd=cost_basis_usd,
            acquisition_date=acquisition_date,
            remaining=amount,
            source="lp_add",
            tx_hash=tx_hash,
        )
        self.add_lot(lot)

    def consume_lp_proportional(
        self,
        lp_token: str,
        lp_amount_removed: Decimal,
        removal_date: datetime,
        method: str,
    ) -> tuple[list[LotConsumption], Decimal]:
        """
        Remove LP lots proportionally.

        Returns (consumptions, total_cost_basis_consumed).
        The caller allocates that cost basis proportionally across
        the received tokens.
        """
        return self._consume_lots_ordered(
            token=lp_token,
            amount=lp_amount_removed,
            disposal_date=removal_date,
            order="fifo",
            method=method,
        )

    # ── Core lot consumption ──────────────────────────────────────────────

    def consume(
        self,
        token: str,
        amount: Decimal,
        disposal_date: datetime,
        order: str,         # "fifo" | "lifo" | "hifo"
        method: str,        # label stored on Disposal
    ) -> tuple[list[LotConsumption], Decimal]:
        """
        Consume `amount` of `token` using the given lot-selection order.

        Returns (consumptions, total_cost_basis_consumed).

        Raises ValueError if insufficient lots exist for this token.
        """
        return self._consume_lots_ordered(token, amount, disposal_date, order, method)

    def _consume_lots_ordered(
        self,
        token: str,
        amount: Decimal,
        disposal_date: datetime,
        order: str,
        method: str,
    ) -> tuple[list[LotConsumption], Decimal]:
        open_lots = self.open_lots(token)
        if not open_lots:
            raise ValueError(f"No open lots for token {token!r}")

        sorted_lots = _sort_lots(open_lots, order)

        consumptions: list[LotConsumption] = []
        remaining_to_consume = amount
        total_cost = Decimal("0")

        for lot in sorted_lots:
            if remaining_to_consume <= Decimal("0"):
                break
            to_take = min(lot.remaining, remaining_to_consume)
            cost_taken = to_take * lot.cost_per_unit

            lot.remaining -= to_take
            remaining_to_consume -= to_take
            total_cost += cost_taken

            consumptions.append(
                LotConsumption(
                    lot_id=lot.id,
                    token=token,
                    amount_consumed=to_take,
                    cost_basis_consumed=cost_taken,
                    acquisition_date=lot.acquisition_date,
                )
            )

        if remaining_to_consume > Decimal("0.00000001"):
            raise ValueError(
                f"Insufficient lots for {token}: needed {amount}, "
                f"short by {remaining_to_consume}"
            )

        return consumptions, total_cost

    # ── Bridge / self-transfer cost carry-over ────────────────────────────

    def carry_over(self, token: str, from_tx: str, to_tx: str, to_date: datetime) -> None:
        """
        Bridge / self-transfer: keep existing lots intact.

        Nothing to do in the in-memory model - lots already reflect the
        correct remaining balances.  This is a no-op but explicit for
        documentation purposes.
        """

    # ── Wrapped token handling ────────────────────────────────────────────

    def wrap(
        self,
        source_token: str,
        dest_token: str,
        amount: Decimal,
        wrap_date: datetime,
        tx_hash: str,
        lot_id_fn,
    ) -> None:
        """
        Wrap source_token → dest_token (e.g. ETH → wETH).

        Tax treatment: NOT a disposal.  Transfer the cost basis from
        source lots to a new dest_token lot.
        """
        consumptions, cost = self._consume_lots_ordered(
            source_token, amount, wrap_date, "fifo", "WRAP"
        )
        # Create a synthetic lot for the wrapped token
        lot = TaxLot(
            id=lot_id_fn(),
            token=dest_token,
            amount=amount,
            cost_basis_usd=cost,
            acquisition_date=wrap_date,
            remaining=amount,
            source="wrap",
            tx_hash=tx_hash,
        )
        self.add_lot(lot)


# ---------------------------------------------------------------------------
# Lot ordering helpers
# ---------------------------------------------------------------------------

def _sort_lots(lots: list[TaxLot], order: str) -> list[TaxLot]:
    """Return lots in the consumption order for a given method."""
    if order == "fifo":
        return sorted(lots, key=lambda l: l.acquisition_date)
    elif order == "lifo":
        return sorted(lots, key=lambda l: l.acquisition_date, reverse=True)
    elif order == "hifo":
        return sorted(lots, key=lambda l: l.cost_per_unit, reverse=True)
    else:
        raise ValueError(f"Unknown lot order: {order!r}")
