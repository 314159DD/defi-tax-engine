"""
FIFO (First In, First Out) lot selection.

Consumes the oldest acquisition lots first.
Generally results in more long-term gains (lower tax rate) for
assets that have appreciated over time.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.calculator.lots import Disposal, LotConsumption, LotManager, holding_period


def consume_fifo(
    lot_manager: LotManager,
    token: str,
    amount: Decimal,
    proceeds_usd: Decimal,
    disposal_date: datetime,
    tx_hash: str,
) -> Disposal:
    """
    Consume `amount` of `token` using FIFO order and return a Disposal.

    Oldest lots are consumed first (smallest acquisition_date first).

    Args:
        lot_manager:   the shared in-memory lot book
        token:         e.g. "ETH"
        amount:        units being disposed
        proceeds_usd:  total USD received / fair-market-value at disposal
        disposal_date: datetime of the disposal event
        tx_hash:       source transaction

    Returns:
        Disposal with gain_loss_usd, holding_period, and lots_consumed populated.

    Raises:
        ValueError: if there are insufficient lots.
    """
    consumptions, total_cost = lot_manager.consume(
        token=token,
        amount=amount,
        disposal_date=disposal_date,
        order="fifo",
        method="FIFO",
    )

    gain_loss = proceeds_usd - total_cost
    hp = _blended_holding_period(consumptions, disposal_date, amount)

    return Disposal(
        date=disposal_date,
        token=token,
        amount=amount,
        proceeds_usd=proceeds_usd,
        cost_basis_usd=total_cost,
        gain_loss_usd=gain_loss,
        holding_period=hp,
        method="FIFO",
        lots_consumed=consumptions,
        tx_hash=tx_hash,
    )


def _blended_holding_period(
    consumptions: list[LotConsumption],
    disposal_date: datetime,
    total_amount: Decimal,
) -> str:
    """
    Determine holding period for the blended disposal.

    If the majority (by amount) of consumed lots are long-term, mark as
    long-term.  Otherwise short-term.  This is a simplification - real
    Form 8949 splits disposals into separate lines per lot when periods
    differ.  The engine handles that splitting; this function returns the
    dominant period for single-lot or all-same-period disposals.
    """
    if not consumptions:
        return "short-term"

    long_term_amount = Decimal("0")
    for c in consumptions:
        hp = holding_period(c.acquisition_date, disposal_date)
        if hp == "long-term":
            long_term_amount += c.amount_consumed

    if total_amount == Decimal("0"):
        return "short-term"

    if long_term_amount / total_amount >= Decimal("0.5"):
        return "long-term"
    return "short-term"
