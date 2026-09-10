"""
IRS Form 8949 generator.

Box codes (per IRS instructions):
  A = short-term, reported on 1099-B with basis
  B = short-term, reported on 1099-B without basis
  C = short-term, NOT reported on 1099-B (self-reported)
  D = long-term, reported on 1099-B with basis
  E = long-term, reported on 1099-B without basis
  F = long-term, NOT reported on 1099-B (self-reported)

1099-DA (new 2026 IRS requirement): brokers report crypto disposals directly
to the IRS. We track which disposals come from 1099-DA brokers vs self-reported.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.storage.database import Database, DisposalRepository

# Brokers known to issue 1099-DA (expand as IRS guidance clarifies)
_1099_DA_BROKERS: frozenset[str] = frozenset({
    "coinbase", "kraken", "gemini", "binance.us", "robinhood", "paypal",
    "cash app", "etoro", "ftx",  # legacy
})


@dataclass
class Form8949Line:
    """One row on IRS Form 8949."""
    description: str              # e.g. "0.5 ETH"
    date_acquired: str            # MM/DD/YYYY  or "VARIOUS"
    date_sold: str                # MM/DD/YYYY
    proceeds: Decimal             # total proceeds USD
    cost_basis: Decimal           # total cost basis USD
    gain_loss: Decimal            # proceeds - cost_basis (+ any adjustments)
    holding_period: str           # "short" | "long"
    box: str                      # A/B/C/D/E/F
    adjustment_code: str = ""     # e.g. "W" for wash sale
    adjustment_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    is_1099_reported: bool = False
    tx_hash: str = ""


def _fmt_date(dt_str: str) -> str:
    """Convert ISO timestamp or YYYY-MM-DD to MM/DD/YYYY."""
    try:
        dt = datetime.fromisoformat(dt_str[:10])
        return dt.strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return dt_str


def _box_code(holding_period: str, is_reported: bool, has_basis: bool) -> str:
    """Determine the Form 8949 checkbox code."""
    if holding_period == "short":
        if is_reported and has_basis:
            return "A"
        if is_reported and not has_basis:
            return "B"
        return "C"
    # long-term
    if is_reported and has_basis:
        return "D"
    if is_reported and not has_basis:
        return "E"
    return "F"


class Form8949Generator:
    """Generates IRS Form 8949 from disposal records."""

    def __init__(self, db: Database) -> None:
        self._disposal_repo = DisposalRepository(db)

    def generate(
        self,
        year: int,
        method: str = "FIFO",
        broker_map: Optional[dict[str, str]] = None,
    ) -> tuple[list[Form8949Line], list[Form8949Line]]:
        """
        Returns (part_i_short_term, part_ii_long_term).

        broker_map: tx_hash -> broker_name, used to flag 1099-DA reported disposals.
        """
        broker_map = broker_map or {}
        disposals = self._disposal_repo.get_by_year(year, method)

        short_term: list[Form8949Line] = []
        long_term: list[Form8949Line] = []

        for d in disposals:
            broker = broker_map.get(d["tx_hash"], "").lower()
            is_reported = broker in _1099_DA_BROKERS
            has_basis = is_reported  # if broker reports, they report basis too

            box = _box_code(d["holding_period"], is_reported, has_basis)
            line = Form8949Line(
                description=f"{d['amount']:.8f} {d['token']}".rstrip("0").rstrip("."),
                date_acquired="VARIOUS",   # we don't store per-disposal acq date yet
                date_sold=_fmt_date(d["disposal_date"]),
                proceeds=d["proceeds_usd"],
                cost_basis=d["cost_basis_usd"],
                gain_loss=d["gain_loss_usd"],
                holding_period=d["holding_period"],
                box=box,
                is_1099_reported=is_reported,
                tx_hash=d["tx_hash"],
            )

            if d["holding_period"] == "short":
                short_term.append(line)
            else:
                long_term.append(line)

        return short_term, long_term

    def to_csv(
        self,
        year: int,
        method: str = "FIFO",
        broker_map: Optional[dict[str, str]] = None,
    ) -> str:
        """Return Form 8949 data as IRS-compatible CSV string."""
        short_term, long_term = self.generate(year, method, broker_map)

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Part", "Box", "Description", "Date Acquired", "Date Sold",
            "Proceeds", "Cost Basis", "Adjustment Code", "Adjustment Amount",
            "Gain or Loss", "1099-DA Reported",
        ]
        writer.writerow(headers)

        for line in short_term:
            writer.writerow([
                "I (Short-Term)", line.box, line.description,
                line.date_acquired, line.date_sold,
                str(line.proceeds), str(line.cost_basis),
                line.adjustment_code, str(line.adjustment_amount),
                str(line.gain_loss), "Yes" if line.is_1099_reported else "No",
            ])

        for line in long_term:
            writer.writerow([
                "II (Long-Term)", line.box, line.description,
                line.date_acquired, line.date_sold,
                str(line.proceeds), str(line.cost_basis),
                line.adjustment_code, str(line.adjustment_amount),
                str(line.gain_loss), "Yes" if line.is_1099_reported else "No",
            ])

        return output.getvalue()

    def summary(self, year: int, method: str = "FIFO") -> dict:
        """Return totals by part for Schedule D reconciliation."""
        short_term, long_term = self.generate(year, method)

        def _totals(lines: list[Form8949Line]) -> dict:
            return {
                "proceeds": sum(l.proceeds for l in lines),
                "cost_basis": sum(l.cost_basis for l in lines),
                "gain_loss": sum(l.gain_loss for l in lines),
                "count": len(lines),
            }

        return {
            "year": year,
            "method": method,
            "part_i_short_term": _totals(short_term),
            "part_ii_long_term": _totals(long_term),
        }
