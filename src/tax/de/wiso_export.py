"""
WISO Steuer CSV export.

Generates a CSV compatible with WISO Steuer (Buhl Data),
matching the format used by CoinTracking's WISO export.

Columns:
  Typ, Kaufdatum, Kaufkurs, Kaufmenge, Kaufgebuehren,
  Verkaufsdatum, Verkaufskurs, Verkaufmenge, Verkaufsgebuehren,
  Gewinn/Verlust
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

from src.tax.models import HoldingPeriod


def _fmt_date_de(dt) -> str:
    """Format date as DD.MM.YYYY."""
    if isinstance(dt, datetime):
        return dt.strftime("%d.%m.%Y")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt[:10]).strftime("%d.%m.%Y")
        except (ValueError, TypeError):
            return dt
    if hasattr(dt, "strftime"):
        return dt.strftime("%d.%m.%Y")
    return str(dt)


def _fmt_eur(amount: Decimal) -> str:
    """Format as German decimal: 1234,56"""
    return f"{amount:.2f}".replace(".", ",")


def generate_wiso_csv(
    disposals: list,
    year: int,
) -> str:
    """
    Generate WISO Steuer-compatible CSV from Disposal objects.

    Args:
        disposals: list of Disposal objects
        year: tax year to filter

    Returns:
        CSV string in WISO Steuer format (semicolon-delimited)
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow([
        "Typ",
        "Kaufdatum",
        "Kaufkurs",
        "Kaufmenge",
        "Kaufgebuehren",
        "Verkaufsdatum",
        "Verkaufskurs",
        "Verkaufmenge",
        "Verkaufsgebuehren",
        "Gewinn/Verlust",
    ])

    for d in disposals:
        if not hasattr(d.date, "year") or d.date.year != year:
            continue

        # Determine type label
        hp = d.holding_period
        if isinstance(hp, HoldingPeriod):
            is_exempt = hp == HoldingPeriod.EXEMPT
        else:
            is_exempt = str(hp) == "exempt"

        typ = "Steuerfrei" if is_exempt else "Veraeusserung"

        # Compute per-unit prices
        if d.amount > Decimal("0"):
            kaufkurs = d.cost_basis_usd / d.amount
            verkaufskurs = d.proceeds_usd / d.amount
        else:
            kaufkurs = Decimal("0")
            verkaufskurs = Decimal("0")

        # Acquisition date: use earliest lot date if available, else "Verschiedene"
        if hasattr(d, "lots_consumed") and d.lots_consumed:
            acq_date = _fmt_date_de(d.lots_consumed[0].acquisition_date)
        else:
            acq_date = "Verschiedene"

        writer.writerow([
            typ,
            acq_date,
            _fmt_eur(kaufkurs),
            str(d.amount),
            "0,00",  # Buy fees (already included in cost basis)
            _fmt_date_de(d.date),
            _fmt_eur(verkaufskurs),
            str(d.amount),
            "0,00",  # Sell fees (already deducted from proceeds)
            _fmt_eur(d.gain_loss_usd),
        ])

    return output.getvalue()
