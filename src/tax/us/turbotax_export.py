"""
TurboTax / H&R Block / TaxAct compatible CSV export.

Adapted from src/reports/csv_export.py to work with Disposal objects directly.

TurboTax expects (H&R Block extended format, accepted by all three):
  Date Sold, Currency Name, Purchase Date, Cost Basis, Proceeds,
  Gain or Loss, Holding Period, Amount Sold
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from src.tax.models import HoldingPeriod


def _fmt_date(dt) -> str:
    """Convert datetime to MM/DD/YYYY."""
    if isinstance(dt, datetime):
        return dt.strftime("%m/%d/%Y")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt[:10]).strftime("%m/%d/%Y")
        except (ValueError, TypeError):
            return dt
    return str(dt)


def _hp_label(hp) -> str:
    """Convert holding period to 'Short' or 'Long'."""
    if isinstance(hp, HoldingPeriod):
        if hp == HoldingPeriod.SHORT_TERM:
            return "Short"
        return "Long"
    s = str(hp)
    if s in ("short-term", "short", "SHORT_TERM"):
        return "Short"
    return "Long"


def generate_turbotax_csv(
    disposals: list,
    year: int,
    method: str,
) -> str:
    """
    Generate TurboTax-compatible CSV from Disposal objects.

    Args:
        disposals: list of Disposal dataclass instances
        year: tax year to filter
        method: cost basis method label

    Returns:
        CSV string ready for TurboTax/H&R Block import
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Date Sold",
        "Currency Name",
        "Purchase Date",
        "Cost Basis",
        "Proceeds",
        "Gain or Loss",
        "Holding Period",
        "Amount Sold",
    ])

    for d in disposals:
        if hasattr(d.date, "year") and d.date.year != year:
            continue

        writer.writerow([
            _fmt_date(d.date),
            d.token,
            "VARIOUS",
            str(d.cost_basis_usd),
            str(d.proceeds_usd),
            str(d.gain_loss_usd),
            _hp_label(d.holding_period),
            str(d.amount),
        ])

    return output.getvalue()
