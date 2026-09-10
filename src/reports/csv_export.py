"""
TurboTax / H&R Block / TaxAct compatible CSV export.

TurboTax expects these columns (crypto import format):
  Currency Name, Purchase Date, Cost Basis, Date Sold, Proceeds

H&R Block / TaxAct compatible format adds:
  Date, Type, Exchange, Asset, Amount, Proceeds, Cost Basis, Gain/Loss

We output the H&R Block extended format which all three major platforms accept.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

from src.storage.database import Database, DisposalRepository


def _fmt_date(iso_str: str) -> str:
    """Convert ISO timestamp to MM/DD/YYYY."""
    try:
        return datetime.fromisoformat(iso_str[:10]).strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return iso_str


class TurboTaxExporter:
    """Exports disposals as TurboTax/H&R Block compatible CSV."""

    def __init__(self, db: Database) -> None:
        self._disposal_repo = DisposalRepository(db)

    def export(self, year: int, method: str = "FIFO") -> str:
        """
        Returns CSV string ready for import into TurboTax, H&R Block, or TaxAct.

        Columns (H&R Block extended):
          Date Sold, Currency Name, Purchase Date, Cost Basis, Proceeds,
          Gain or Loss, Holding Period, Amount Sold
        """
        disposals = self._disposal_repo.get_by_year(year, method)

        output = io.StringIO()
        writer = csv.writer(output)

        # TurboTax Premier / H&R Block Deluxe accept this exact header
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
            writer.writerow([
                _fmt_date(d["disposal_date"]),
                d["token"],
                "VARIOUS",                    # multiple lots may have been consumed
                str(d["cost_basis_usd"]),
                str(d["proceeds_usd"]),
                str(d["gain_loss_usd"]),
                d["holding_period"].title(),   # Short / Long
                str(d["amount"]),
            ])

        return output.getvalue()

    def export_full_detail(self, year: int, method: str = "FIFO") -> str:
        """
        Extended export with extra metadata for record-keeping.
        Not required for tax software import, but useful for audit trail.
        """
        disposals = self._disposal_repo.get_by_year(year, method)

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "Date Sold", "Currency Name", "Amount Sold",
            "Proceeds (USD)", "Cost Basis (USD)", "Gain/Loss (USD)",
            "Holding Period", "Method", "TX Hash",
        ])

        for d in disposals:
            writer.writerow([
                _fmt_date(d["disposal_date"]),
                d["token"],
                str(d["amount"]),
                str(d["proceeds_usd"]),
                str(d["cost_basis_usd"]),
                str(d["gain_loss_usd"]),
                d["holding_period"].title(),
                d["method"],
                d["tx_hash"],
            ])

        return output.getvalue()
