"""
IRS Form 8949 generator - standalone functions for the tax module system.

Adapted from src/reports/form_8949.py to work with Disposal objects directly
(instead of DB rows), enabling use from the TaxModule.generate_reports() flow.

Box codes (per IRS instructions):
  A = short-term, reported on 1099-B with basis
  B = short-term, reported on 1099-B without basis
  C = short-term, NOT reported on 1099-B (self-reported)
  D = long-term, reported on 1099-B with basis
  E = long-term, reported on 1099-B without basis
  F = long-term, NOT reported on 1099-B (self-reported)
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.tax.models import HoldingPeriod

# Brokers known to issue 1099-DA
_1099_DA_BROKERS: frozenset[str] = frozenset({
    "coinbase", "kraken", "gemini", "binance.us", "robinhood", "paypal",
    "cash app", "etoro",
})


def _fmt_date(dt) -> str:
    """Convert datetime or ISO string to MM/DD/YYYY."""
    if isinstance(dt, datetime):
        return dt.strftime("%m/%d/%Y")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt[:10]).strftime("%m/%d/%Y")
        except (ValueError, TypeError):
            return dt
    return str(dt)


def _box_code(holding_period: str, is_reported: bool, has_basis: bool) -> str:
    """Determine the Form 8949 checkbox code."""
    is_short = holding_period in ("short-term", "short", "SHORT_TERM")
    if is_short:
        if is_reported and has_basis:
            return "A"
        if is_reported:
            return "B"
        return "C"
    # long-term or exempt (exempt disposals in US shouldn't happen, but handle gracefully)
    if is_reported and has_basis:
        return "D"
    if is_reported:
        return "E"
    return "F"


def generate_form_8949_csv(
    disposals: list,
    year: int,
    method: str,
    broker_map: Optional[dict[str, str]] = None,
) -> str:
    """
    Generate Form 8949 CSV from Disposal objects.

    Args:
        disposals: list of Disposal dataclass instances
        year: tax year to filter
        method: cost basis method label
        broker_map: tx_hash -> broker_name for 1099-DA flagging

    Returns:
        CSV string
    """
    broker_map = broker_map or {}

    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "Part", "Box", "Description", "Date Acquired", "Date Sold",
        "Proceeds", "Cost Basis", "Adjustment Code", "Adjustment Amount",
        "Gain or Loss", "1099-DA Reported",
    ]
    writer.writerow(headers)

    for d in disposals:
        # Filter by year
        disposal_date = d.date if hasattr(d, "date") else d.get("date")
        if hasattr(disposal_date, "year"):
            if disposal_date.year != year:
                continue
        else:
            continue

        broker = broker_map.get(d.tx_hash, "").lower()
        is_reported = broker in _1099_DA_BROKERS
        has_basis = is_reported

        hp = d.holding_period
        if isinstance(hp, HoldingPeriod):
            hp_str = hp.value
        else:
            hp_str = str(hp)

        is_short = hp_str in ("short-term", "short", "SHORT_TERM")
        part = "I (Short-Term)" if is_short else "II (Long-Term)"
        box = _box_code(hp_str, is_reported, has_basis)

        description = f"{d.amount:.8f} {d.token}".rstrip("0").rstrip(".")

        writer.writerow([
            part, box, description,
            "VARIOUS", _fmt_date(d.date),
            str(d.proceeds_usd), str(d.cost_basis_usd),
            "", "0",
            str(d.gain_loss_usd),
            "Yes" if is_reported else "No",
        ])

    return output.getvalue()
