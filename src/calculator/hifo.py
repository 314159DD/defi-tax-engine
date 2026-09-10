"""
HIFO (Highest In, First Out) lot selection.

Consumes the lots with the highest cost-per-unit first.
This minimizes taxable gain (or maximizes deductible loss) and is
generally the most tax-efficient method for appreciating assets.

Note: HIFO is a specific identification method recognized by the IRS for
crypto assets.  Taxpayers must be able to specifically identify the lots
(i.e., have records of cost basis per lot).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.calculator.lots import Disposal, LotConsumption, LotManager, holding_period


def consume_hifo(
    lot_manager: LotManager,
    token: str,
    amount: Decimal,
    proceeds_usd: Decimal,
    disposal_date: datetime,
    tx_hash: str,
) -> Disposal:
    """
    Consume `amount` of `token` using HIFO order and return a Disposal.

    Lots with the highest cost-per-unit are consumed first.

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
        order="hifo",
        method="HIFO",
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
        method="HIFO",
        lots_consumed=consumptions,
        tx_hash=tx_hash,
    )


def _blended_holding_period(
    consumptions: list[LotConsumption],
    disposal_date: datetime,
    total_amount: Decimal,
) -> str:
    """Return dominant holding period (long-term if >= 50% of amount is long-term)."""
    if not consumptions or total_amount == Decimal("0"):
        return "short-term"

    long_term_amount = Decimal("0")
    for c in consumptions:
        hp = holding_period(c.acquisition_date, disposal_date)
        if hp == "long-term":
            long_term_amount += c.amount_consumed

    if long_term_amount / total_amount >= Decimal("0.5"):
        return "long-term"
    return "short-term"
